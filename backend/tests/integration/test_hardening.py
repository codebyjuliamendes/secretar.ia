"""Endurecimento: exclusão completa do titular (LGPD), exportação segura, locks do agendador, limites de corpo e
de taxa. Nenhuma integração externa é chamada (Gemini, Evolution e SMTP ficam nos providers de teste)."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx

from app.security.signatures import sign_hub
from tests.conftest import auth_headers, register_user, unique_email
from tests.integration.test_rbac_and_admin import login


def signed(payload: dict, secret: str = "test-whatsapp-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, secret), "Content-Type": "application/json"}


async def _inbound(client, tid: str, phone: str, text: str, message_id: str):
    body, headers = signed({"messageId": message_id, "phone": phone, "text": text, "tenantId": tid})
    r = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _staff(client, clean_db, owner) -> dict:
    tid = owner["tenantId"]
    email = unique_email("staff-hard")
    inv = await client.post(
        f"/api/clinic/{tid}/team",
        headers=auth_headers(owner),
        json={"email": email, "name": "Recepção", "role": "STAFF"},
    )
    assert inv.status_code == 201, inv.text
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    token = job.payload["text"].split("token=")[1].split()[0]
    assert (
        await client.post("/api/auth/invites/accept", json={"token": token, "password": "Staff1234"})
    ).status_code == 200
    return auth_headers(await login(client, email, "Staff1234"))


# ------------------------------------------------------------------ LGPD --


async def test_deleting_a_patient_erases_conversation_and_queue_but_not_other_contacts(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    other = await register_user(client, clinic="Outra Clínica")
    gone, stays = "5581999992001", "5581999992002"

    await _inbound(client, tid, gone, "oi, quanto custa a limpeza?", "h1")
    await _inbound(client, tid, gone, "quero falar com um atendente", "h2")  # gera aviso na inbox com o telefone
    await _inbound(client, tid, stays, "bom dia", "h3")
    await _inbound(client, other["tenantId"], gone, "bom dia", "h4")  # mesmo número, outra clínica
    await clean_db.unansweredquestion.create(data={"tenantId": tid, "phone": gone, "question": "vocês fazem x?"})

    assert await clean_db.message.count(where={"tenantId": tid, "phone": gone}) > 0
    assert await clean_db.notification.count(where={"tenantId": tid, "phone": gone}) > 0
    queued = [j for j in await clean_db.job.find_many(where={"name": "send-whatsapp"}) if j.payload["phone"] == gone]
    assert len(queued) == 3  # duas respostas aqui + uma na outra clínica

    patient = await clean_db.patient.find_first(where={"tenantId": tid, "phone": gone})
    r = await client.delete(f"/api/clinic/{tid}/patients/{patient.id}", headers=h)
    assert r.status_code == 204, r.text

    assert await clean_db.patient.count(where={"tenantId": tid, "phone": gone}) == 0
    assert await clean_db.message.count(where={"tenantId": tid, "phone": gone}) == 0
    assert await clean_db.notification.count(where={"tenantId": tid, "phone": gone}) == 0
    assert await clean_db.unansweredquestion.count(where={"tenantId": tid, "phone": gone}) == 0
    left = [j for j in await clean_db.job.find_many(where={"name": "send-whatsapp"}) if j.payload["phone"] == gone]
    assert len(left) == 1 and left[0].payload["tenantId"] == other["tenantId"]

    # Outro contato da mesma clínica e o mesmo número em outra clínica ficam intactos.
    assert await clean_db.message.count(where={"tenantId": tid, "phone": stays}) == 2
    assert await clean_db.message.count(where={"tenantId": other["tenantId"], "phone": gone}) == 2

    audit = await clean_db.auditlog.find_first(where={"action": "patient.deleted"})
    assert audit.metadata["phone"] == "*********2001" and gone not in json.dumps(audit.metadata)
    assert audit.metadata["removed"]["messages"] == 4


async def test_question_about_lgpd_is_not_a_deletion_request(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    out = await _inbound(client, tid, "5581999992010", "Vocês seguem a LGPD?", "q1")
    assert "exclusão" not in out["reply"].lower()
    patient = await clean_db.patient.find_first(where={"tenantId": tid, "phone": "5581999992010"})
    assert patient.marketingOptOut is False

    out = await _inbound(client, tid, "5581999992010", "por favor, apaguem meu cadastro", "q2")
    assert "exclusão" not in out["reply"].lower()  # "apaguem" (3ª pessoa) não está na lista; a equipe vê na conversa
    out = await _inbound(client, tid, "5581999992010", "quero excluir meu cadastro", "q3")
    assert "pedido de exclusão" in out["reply"].lower()


async def test_platform_deletion_purges_queued_jobs_of_the_tenant(client, clean_db):
    reg = await register_user(client, clinic="Some Daqui")
    tid = reg["tenantId"]
    other = await register_user(client, clinic="Fica Aqui")
    await _inbound(client, tid, "5581999992020", "bom dia", "p1")
    await _inbound(client, other["tenantId"], "5581999992021", "bom dia", "p2")
    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    ah = auth_headers(await login(client, admin_user["email"], admin_user["password"]))

    ok = await client.post(f"/api/admin/tenants/{tid}/delete", headers=ah, json={"confirm": "Some Daqui"})
    assert ok.status_code == 200, ok.text
    tenants_in_queue = {
        j.payload.get("tenantId") for j in await clean_db.job.find_many(where={"name": "send-whatsapp"})
    }
    assert tid not in tenants_in_queue and other["tenantId"] in tenants_in_queue


# ------------------------------------------------------------- Exportação --


async def test_export_neutralizes_spreadsheet_formulas_and_is_audited(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    # O nome do perfil do WhatsApp é escolhido pelo próprio contato: vetor clássico de CSV injection.
    body, headers = signed(
        {
            "messageId": "x1",
            "phone": "5581999992030",
            "text": "oi",
            "tenantId": tid,
            "pushName": '=HYPERLINK("http://evil.example","clique")',
        }
    )
    assert (await client.post("/api/webhooks/whatsapp", content=body, headers=headers)).status_code == 200
    await client.post(f"/api/clinic/{tid}/patients", headers=h, json={"phone": "5581999992031", "notes": "@SUM(1+1)"})

    r = await client.get(f"/api/clinic/{tid}/export/patients.csv", headers=h)
    assert r.status_code == 200
    lines = r.text.splitlines()
    assert any(line.startswith("\"'=HYPERLINK(") for line in lines), r.text
    assert "'@SUM(1+1)" in r.text
    assert "+5581999992030" in r.text and "'+5581" not in r.text  # telefone continua legível
    actions = {a.action for a in await clean_db.auditlog.find_many(where={"tenantId": tid})}
    assert "export.patients" in actions


async def test_staff_cannot_bulk_export_but_still_works_the_records(client, clean_db):
    owner = await register_user(client)
    tid = owner["tenantId"]
    hs = await _staff(client, clean_db, owner)
    for path in ("/export/patients.csv", "/export/appointments.csv"):
        r = await client.get(f"/api/clinic/{tid}{path}", headers=hs)
        assert r.status_code == 403 and r.json()["error"]["code"] == "permission_denied"
    assert (await client.get(f"/api/clinic/{tid}/patients", headers=hs)).status_code == 200
    created = await client.post(f"/api/clinic/{tid}/patients", headers=hs, json={"phone": "5581999992040"})
    assert created.status_code == 201


async def test_export_of_another_tenant_is_not_found(client, clean_db):
    a = await register_user(client, clinic="Clínica A")
    b = await register_user(client, clinic="Clínica B")
    r = await client.get(f"/api/clinic/{b['tenantId']}/export/patients.csv", headers=auth_headers(a))
    assert r.status_code == 404


# ------------------------------------------------------- Agendamento público --


async def test_public_booking_refuses_dates_beyond_the_offered_window(client, clean_db):
    reg = await register_user(client, clinic="Longe Demais")
    tid, h = reg["tenantId"], auth_headers(reg)
    slug = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()["slug"]
    far = (datetime.now(UTC) + timedelta(days=400)).replace(hour=13, minute=0, second=0, microsecond=0)
    r = await client.post(
        f"/api/public/booking/{slug}", json={"name": "Teo", "phone": "81999992050", "start": far.isoformat()}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "slot_too_far"
    assert await clean_db.appointment.count(where={"tenantId": tid}) == 0


# ------------------------------------------------------------- Agendador --


async def test_scheduler_lock_is_exclusive_and_released(clean_db):
    from app.jobs.scheduler import exclusive

    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with exclusive(990_001, hold_seconds=30) as won:
            assert won
            entered.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await entered.wait()
    async with exclusive(990_001, hold_seconds=30) as won:
        assert won is False  # outra réplica (outra conexão) não entra
    release.set()
    await task
    async with exclusive(990_001, hold_seconds=30) as won:
        assert won is True  # liberado no fim da transação, sem depender de unlock na mesma conexão


# ------------------------------------------------------ Limites de entrada --


async def test_chunked_body_over_the_limit_is_rejected(clean_db, monkeypatch):
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "max_request_body_bytes", 1024)
    app = create_app(run_background=False)

    async def chunks():
        for _ in range(4):
            yield b"x" * 512

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/webhooks/whatsapp", content=chunks(), headers={"X-Hub-Signature-256": "sha256=00"})
        assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
        ok = await c.get("/health")
        assert ok.status_code == 200


async def test_request_id_from_client_is_sanitized(client):
    r = await client.get("/health", headers={"X-Request-Id": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    r = await client.get("/health", headers={"X-Request-Id": "x" * 500})
    assert len(r.headers["x-request-id"]) == 16
    r = await client.get("/health", headers={"X-Request-Id": "bad id\twith spaces"})
    assert r.headers["x-request-id"] != "bad id\twith spaces"
    assert r.headers["x-frame-options"] == "DENY"


async def test_token_endpoints_are_rate_limited(client):
    statuses = []
    for _ in range(32):
        r = await client.post("/api/auth/reset-password", json={"token": "x" * 20, "password": "Senha1234"})
        statuses.append(r.status_code)
    assert statuses[0] == 400 and statuses[-1] == 429


async def test_change_password_attempts_are_capped_per_user(client, clean_db):
    reg = await register_user(client)
    h = auth_headers(reg)
    codes = []
    for _ in range(11):
        r = await client.post(
            "/api/auth/change-password", headers=h, json={"currentPassword": "errada", "newPassword": "Nova12345"}
        )
        codes.append(r.status_code)
    assert codes[0] == 400 and codes[-1] == 429


async def test_daily_maintenance_redacts_old_ai_log_text_but_keeps_metrics(client, clean_db):
    from app.jobs.scheduler import run_daily_maintenance

    reg = await register_user(client)
    tid = reg["tenantId"]
    old = await clean_db.executionlog.create(
        data={"tenantId": tid, "agent": "secretaria", "intent": "INFO", "input": "meu exame deu X", "output": "ok"}
    )
    await clean_db.execute_raw(
        """UPDATE "ExecutionLog" SET "createdAt" = NOW() - INTERVAL '31 days' WHERE id = $1""", old.id
    )
    recent = await clean_db.executionlog.create(
        data={"tenantId": tid, "agent": "secretaria", "intent": "INFO", "input": "bom dia", "output": "olá"}
    )
    result = await run_daily_maintenance()
    assert result["executionLogsRedacted"] == 1
    old_row = await clean_db.executionlog.find_unique(where={"id": old.id})
    assert old_row.input == "" and old_row.output is None and old_row.intent == "INFO"
    assert (await clean_db.executionlog.find_unique(where={"id": recent.id})).input == "bom dia"
