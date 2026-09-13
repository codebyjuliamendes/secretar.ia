import json
import uuid

from app.security.signatures import sign_hub, sign_stripe
from tests.conftest import auth_headers, register_user


def signed(payload: dict, secret: str = "test-whatsapp-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, secret), "Content-Type": "application/json"}


async def test_whatsapp_webhook_requires_valid_signature(client, clean_db):
    reg = await register_user(client)
    payload = {"messageId": "m1", "phone": "5581999990000", "text": "oi", "tenantId": reg["tenantId"]}
    assert (await client.post("/api/webhooks/whatsapp", json=payload)).status_code == 401
    body, headers = signed(payload, secret="wrong")
    assert (await client.post("/api/webhooks/whatsapp", content=body, headers=headers)).status_code == 401
    assert await clean_db.processedmessage.count() == 0


async def test_whatsapp_webhook_full_flow_idempotent_and_scoped(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE"})
    payload = {
        "messageId": "msg-1",
        "phone": "+55 81 99999-0000",
        "text": "Quero agendar botox",
        "tenantId": tid,
        "pushName": "Amanda",
    }
    body, headers = signed(payload)
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "processed" and data["intent"] == "AGENDAR" and data["degraded"] is True

    dup = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert dup.json()["status"] == "duplicate_ignored"

    # Efeitos: paciente criado, memória gravada, job de envio enfileirado, uso contabilizado.
    patients = (await client.get(f"/api/clinic/{tid}/patients", headers=auth_headers(reg))).json()
    assert patients["total"] == 1 and patients["items"][0]["name"] == "Amanda"
    assert patients["items"][0]["phone"] == "5581999990000"
    assert await clean_db.message.count(where={"tenantId": tid}) == 2
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"})
    assert len(jobs) == 1 and jobs[0].payload["tenantId"] == tid
    usage = await clean_db.usagecounter.find_first(where={"tenantId": tid})
    assert usage is None  # resposta por regras (sem IA) não consome a quota de mensagens de IA

    # Mesmo messageId em OUTRO tenant é uma mensagem distinta (idempotência é por tenant).
    other = await register_user(client)
    await clean_db.tenant.update(where={"id": other["tenantId"]}, data={"status": "ACTIVE"})
    body2, headers2 = signed({**payload, "tenantId": other["tenantId"]})
    assert (await client.post("/api/webhooks/whatsapp", content=body2, headers=headers2)).json()[
        "status"
    ] == "processed"

    # Handoff humano gera notificação na inbox.
    body3, headers3 = signed({**payload, "messageId": "msg-3", "text": "quero falar com um atendente"})
    assert (await client.post("/api/webhooks/whatsapp", content=body3, headers=headers3)).json()["intent"] == "HUMANO"
    inbox = (await client.get(f"/api/clinic/{tid}/notifications", headers=auth_headers(reg))).json()
    assert any(n["type"] == "HUMAN_HANDOFF" for n in inbox["items"])
    assert (await client.post(f"/api/clinic/{tid}/notifications/read", headers=auth_headers(reg))).json()[
        "updated"
    ] >= 1


async def test_whatsapp_webhook_blocked_when_tenant_not_operational_or_over_quota(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "PAST_DUE"})
    body, headers = signed({"messageId": "b1", "phone": "5581999990001", "text": "oi", "tenantId": tid})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.json()["status"] == "blocked" and res.json()["reason"] == "tenant_past_due"
    assert await clean_db.job.count(where={"name": "send-whatsapp"}) == 0

    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE", "plan": "BASIC"})
    from app.services.usage import AI_MESSAGES, current_period

    await clean_db.usagecounter.create(
        data={"tenantId": tid, "period": current_period(), "metric": AI_MESSAGES, "count": 1500}
    )
    # Cota estourada NÃO corta por padrão: a assistente segue respondendo (a Júlia decide o upgrade com o cliente).
    body, headers = signed({"messageId": "b2", "phone": "5581999990001", "text": "oi", "tenantId": tid})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.json()["status"] == "processed"
    # Só corta quando o admin liga "cortar ao estourar" na conta.
    await clean_db.tenant.update(where={"id": tid}, data={"hardLimit": True})
    body, headers = signed({"messageId": "b3", "phone": "5581999990001", "text": "oi", "tenantId": tid})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.json()["status"] == "blocked" and res.json()["reason"] == "quota_exceeded"


async def test_evolution_webhook_token_and_instance_resolution(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE", "whatsappInstance": "inst-abc"})
    evo = {
        "event": "messages.upsert",
        "instance": "inst-abc",
        "data": {
            "key": {"remoteJid": "5581988880000@s.whatsapp.net", "fromMe": False, "id": str(uuid.uuid4())},
            "pushName": "Bia",
            "message": {"conversation": "qual o valor do peeling?"},
        },
    }
    assert (await client.post("/api/webhooks/evolution/token-errado", json=evo)).status_code == 401
    ok = await client.post("/api/webhooks/evolution/test-evolution-token", json=evo)
    assert ok.status_code == 200 and ok.json()["status"] == "processed" and ok.json()["intent"] == "INFO"
    unknown = await client.post("/api/webhooks/evolution/test-evolution-token", json={**evo, "instance": "nope"})
    assert unknown.json()["reason"] == "unknown_instance"
    conn = await client.post(
        "/api/webhooks/evolution/test-evolution-token",
        json={"event": "connection.update", "instance": "inst-abc", "data": {"state": "open"}},
    )
    assert conn.json()["status"] == "connection_updated"
    t = await clean_db.tenant.find_unique(where={"id": tid})
    assert t.whatsappConnected is True


async def test_billing_webhook_signature_idempotency_and_status(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    event = {
        "id": "evt_100",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "object": "invoice",
                "subscription": "sub_100",
                "customer": "cus_100",
                "metadata": {"tenantId": tid, "plan": "PRO"},
            }
        },
    }
    body = json.dumps(event).encode()
    assert (
        await client.post("/api/webhooks/billing", content=body, headers={"Content-Type": "application/json"})
    ).status_code == 401
    bad_sig = sign_stripe(body, "whsec_wrong")
    assert (
        await client.post(
            "/api/webhooks/billing",
            content=body,
            headers={"Stripe-Signature": bad_sig, "Content-Type": "application/json"},
        )
    ).status_code == 401
    t = await clean_db.tenant.find_unique(where={"id": tid})
    assert str(t.status) == "ACTIVE" and t.subscriptionId is None  # evento sem assinatura válida não foi aplicado

    good = {"Stripe-Signature": sign_stripe(body, "whsec_test"), "Content-Type": "application/json"}
    res = await client.post("/api/webhooks/billing", content=body, headers=good)
    assert res.status_code == 200 and res.json()["handled"] is True and res.json()["status"] == "ACTIVE"
    t = await clean_db.tenant.find_unique(where={"id": tid})
    assert str(t.plan) == "PRO" and t.subscriptionId == "sub_100"
    dup = await client.post("/api/webhooks/billing", content=body, headers=good)
    assert dup.json()["reason"] == "duplicate"

    failed = {
        "id": "evt_101",
        "type": "invoice.payment_failed",
        "data": {"object": {"object": "invoice", "subscription": "sub_100"}},
    }
    body2 = json.dumps(failed).encode()
    res2 = await client.post(
        "/api/webhooks/billing",
        content=body2,
        headers={"Stripe-Signature": sign_stripe(body2, "whsec_test"), "Content-Type": "application/json"},
    )
    assert res2.json()["status"] == "PAST_DUE"
    billing = await client.get(f"/api/clinic/{tid}/billing", headers=auth_headers(reg))
    assert billing.json()["status"] == "PAST_DUE" and billing.json()["usage"]["aiMessages"]["limit"] == 4000


async def test_queue_claim_is_atomic_and_backoff_recovers(client, clean_db):
    from app.jobs import tasks  # noqa: F401
    from app.jobs.queue import claim_next_job, enqueue, recover_stuck_jobs, run_job

    reg = await register_user(client)
    await clean_db.job.delete_many()  # descarta o e-mail de verificação do cadastro
    job_id = await enqueue("send-whatsapp", {"tenantId": reg["tenantId"], "phone": "5581999990000", "text": "olá"})
    first = await claim_next_job()
    second = await claim_next_job()
    assert first and first["id"] == job_id and second is None  # só um worker leva o job
    await run_job(first)  # provider console em ambiente de teste
    done = await clean_db.job.find_unique(where={"id": job_id})
    assert str(done.status) == "COMPLETED"

    bad_id = await enqueue("send-whatsapp", {"tenantId": "inexistente", "phone": "1", "text": "x"})
    await run_job(await claim_next_job())
    bad = await clean_db.job.find_unique(where={"id": bad_id})
    assert str(bad.status) == "FAILED" and "permanente" in bad.error

    # Job preso em RUNNING é recuperado.
    stuck = await enqueue("send-whatsapp", {"tenantId": reg["tenantId"], "phone": "5581999990000", "text": "y"})
    await clean_db.execute_raw(
        """UPDATE "Job" SET status='RUNNING', "lockedAt" = NOW() - INTERVAL '30 minutes' WHERE id = $1""",
        stuck,
    )
    assert await recover_stuck_jobs(10) == 1
    assert str((await clean_db.job.find_unique(where={"id": stuck})).status) == "PENDING"


async def test_cron_and_health(client, clean_db):
    assert (await client.get("/health")).status_code == 200
    assert (await client.post("/api/internal/cron/upsell")).status_code == 401
    ok = await client.post("/api/internal/cron/upsell", headers={"Authorization": "Bearer test-cron-secret"})
    assert ok.status_code == 200 and "messagesQueued" in ok.json()


async def test_upsell_campaign_targets_and_idempotency(client, clean_db):
    from datetime import UTC, datetime, timedelta

    from app.services.marketing import run_upsell_campaign

    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(
        where={"id": tid},
        data={"status": "ACTIVE", "plan": "BASIC", "upsellEnabled": True, "upsellDays": 150},
    )
    p = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581977770000", "name": "Carla"})
    await clean_db.appointment.create(
        data={
            "tenantId": tid,
            "patientId": p.id,
            "service": "Toxina",
            "date": datetime.now(UTC) - timedelta(days=152),
            "status": "COMPLETED",
        }
    )
    r1 = await run_upsell_campaign(tenant_id=tid)
    assert r1["messagesQueued"] == 1
    r2 = await run_upsell_campaign(tenant_id=tid)
    assert r2["messagesQueued"] == 0  # já disparado para este agendamento
    job = await clean_db.job.find_first(where={"name": "send-whatsapp"})
    assert "Carla" in job.payload["text"]


async def test_first_contact_gets_the_assistant_introduction_once(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"niche": "pet"})
    payload = {"messageId": "i1", "phone": "5581999990077", "text": "oi", "tenantId": tid, "pushName": "Bia"}
    body, headers = signed(payload)
    assert (await client.post("/api/webhooks/whatsapp", content=body, headers=headers)).json()["status"] == "processed"
    first = (await clean_db.job.find_many(where={"name": "send-whatsapp"}))[0].payload["text"]
    assert first.startswith("Olá! Sou a assistente virtual da ") and "seu pet" in first and chr(10) * 2 in first
    # Segunda mensagem da mesma pessoa: sem apresentação.
    body, headers = signed({**payload, "messageId": "i2", "text": "quanto custa o banho?"})
    assert (await client.post("/api/webhooks/whatsapp", content=body, headers=headers)).json()["status"] == "processed"
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"}, order={"createdAt": "asc"})
    assert len(jobs) == 2 and "seu pet" not in jobs[1].payload["text"]
    # Cliente pode desligar a apresentação.
    await client.patch(f"/api/clinic/{tid}/settings", headers=auth_headers(reg), json={"introEnabled": False})
    body, headers = signed({"messageId": "i3", "phone": "5581999990078", "text": "oi", "tenantId": tid})
    await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"}, order={"createdAt": "asc"})
    assert len(jobs) == 3 and "seu pet" not in jobs[2].payload["text"]


async def test_quota_alerts_at_80_and_100_percent_notify_clinic_and_team(client, clean_db, monkeypatch):
    from app.config import get_settings
    from app.services import quota_alerts

    reg = await register_user(client, plan="BASIC")  # 1.500 mensagens/mês
    tenant = await clean_db.tenant.find_unique(where={"id": reg["tenantId"]})
    settings = get_settings()
    monkeypatch.setattr(type(settings), "alerts_to", property(lambda self: "julia@example.com"))
    await quota_alerts.after_ai_message(settings, tenant, 1199)  # abaixo do gatilho: nada
    assert await clean_db.notification.count(where={"tenantId": tenant.id, "type": "BILLING"}) == 0
    await quota_alerts.after_ai_message(settings, tenant, 1200)  # 80% exato
    await quota_alerts.after_ai_message(settings, tenant, 1200)  # repetido (retentativa): deduplicado
    await quota_alerts.after_ai_message(settings, tenant, 1500)  # 100%
    notes = await clean_db.notification.find_many(where={"tenantId": tenant.id, "type": "BILLING"})
    titles = sorted(n.title for n in notes)
    assert len(titles) == 2 and titles[0].startswith("80% das mensagens") and titles[1].startswith("Limite mensal")
    assert "continua respondendo" in [n for n in notes if n.title.startswith("Limite")][0].body
    mails = await clean_db.job.find_many(where={"name": "send-email"})
    mails = [m for m in mails if m.payload["subject"].startswith("[Secretar.ia]")]  # fora o e-mail de confirmação
    assert len(mails) == 2 and all(m.payload["to"] == "julia@example.com" for m in mails)
    assert any("80%" in m.payload["subject"] for m in mails) and any("estourou" in m.payload["subject"] for m in mails)
