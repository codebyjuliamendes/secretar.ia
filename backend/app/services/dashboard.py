"""Métricas reais do painel da clínica (sem números inventados)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import db
from app.services.usage import usage_summary


def _n(v) -> int:
    return int(v or 0)


async def clinic_dashboard(tenant, *, days: int = 30) -> dict:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    prev_since = since - timedelta(days=days)

    kpis = await db.query_raw(
        """
        SELECT
          (SELECT COUNT(*) FROM "Patient" WHERE "tenantId" = $1) AS patients_total,
          (SELECT COUNT(*) FROM "Patient" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz) AS patients_new,
          (SELECT COUNT(*) FROM "Patient" WHERE "tenantId" = $1
              AND "createdAt" >= $3::timestamptz AND "createdAt" < $2::timestamptz) AS patients_new_prev,
          (SELECT COUNT(*) FROM "Appointment" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz)
              AS appts_created,
          (SELECT COUNT(*) FROM "Appointment" WHERE "tenantId" = $1
              AND "createdAt" >= $3::timestamptz AND "createdAt" < $2::timestamptz) AS appts_created_prev,
          (SELECT COUNT(*) FROM "Appointment" WHERE "tenantId" = $1 AND status = 'PENDING') AS appts_pending,
          (SELECT COUNT(*) FROM "Appointment" WHERE "tenantId" = $1 AND status = 'CONFIRMED' AND date >= NOW())
              AS appts_upcoming,
          (SELECT COALESCE(SUM("priceCents"),0) FROM "Appointment"
              WHERE "tenantId" = $1 AND status = 'COMPLETED' AND date >= $2::timestamptz) AS revenue_completed_cents,
          (SELECT COALESCE(SUM("priceCents"),0) FROM "Appointment"
              WHERE "tenantId" = $1 AND status = 'COMPLETED' AND source = 'AI' AND date >= $2::timestamptz)
              AS revenue_ai_cents,
          (SELECT COUNT(*) FROM "Appointment" WHERE "tenantId" = $1 AND source = 'AI'
              AND "createdAt" >= $2::timestamptz) AS appts_ai,
          (SELECT COUNT(*) FROM "Notification" WHERE "tenantId" = $1 AND type = 'HUMAN_HANDOFF'
              AND "createdAt" >= $2::timestamptz) AS handoffs,
          (SELECT COUNT(*) FROM "Notification" WHERE "tenantId" = $1 AND "readAt" IS NULL) AS unread,
          (SELECT COUNT(*) FROM "ExecutionLog" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz) AS ai_messages,
          (SELECT COUNT(*) FROM "ExecutionLog"
              WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz AND error IS NOT NULL) AS ai_degraded,
          (SELECT AVG("runTimeMs") FROM "ExecutionLog"
              WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz) AS ai_avg_ms
        """,
        tenant.id,
        since,
        prev_since,
    )
    k = kpis[0] if kpis else {}

    series_rows = await db.query_raw(
        """
        SELECT d::date AS day,
               COALESCE(a.cnt, 0) AS appointments,
               COALESCE(m.cnt, 0) AS messages
        FROM generate_series(($2::timestamptz)::date, (NOW() AT TIME ZONE 'UTC')::date, '1 day') d
        LEFT JOIN (SELECT "createdAt"::date AS day, COUNT(*) cnt FROM "Appointment"
                   WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz GROUP BY 1) a ON a.day = d::date
        LEFT JOIN (SELECT "createdAt"::date AS day, COUNT(*) cnt FROM "ExecutionLog"
                   WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz GROUP BY 1) m ON m.day = d::date
        ORDER BY d
        """,
        tenant.id,
        since,
    )
    intents = await db.query_raw(
        """SELECT COALESCE(intent,'INFO') AS intent, COUNT(*) cnt FROM "ExecutionLog"
           WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamptz GROUP BY 1 ORDER BY 2 DESC""",
        tenant.id,
        since,
    )
    recent = await db.appointment.find_many(
        where={"tenantId": tenant.id}, include={"patient": True}, order={"createdAt": "desc"}, take=8
    )
    return {
        "periodDays": days,
        "kpis": {
            "patientsTotal": _n(k.get("patients_total")),
            "patientsNew": _n(k.get("patients_new")),
            "patientsNewPrev": _n(k.get("patients_new_prev")),
            "appointmentsCreated": _n(k.get("appts_created")),
            "appointmentsCreatedPrev": _n(k.get("appts_created_prev")),
            "appointmentsPending": _n(k.get("appts_pending")),
            "appointmentsUpcoming": _n(k.get("appts_upcoming")),
            "appointmentsByAI": _n(k.get("appts_ai")),
            "revenueCompletedCents": _n(k.get("revenue_completed_cents")),
            "revenueFromAICents": _n(k.get("revenue_ai_cents")),
            "humanHandoffs": _n(k.get("handoffs")),
            "unreadNotifications": _n(k.get("unread")),
            "aiMessages": _n(k.get("ai_messages")),
            "aiDegraded": _n(k.get("ai_degraded")),
            "aiAvgResponseMs": int(float(k.get("ai_avg_ms") or 0)),
        },
        "series": [
            {"day": str(r["day"])[:10], "appointments": _n(r["appointments"]), "messages": _n(r["messages"])}
            for r in series_rows
        ],
        "intents": [{"intent": r["intent"], "count": _n(r["cnt"])} for r in intents],
        "recentAppointments": [
            {
                "id": a.id,
                "patientName": (a.patient.name if a.patient and a.patient.name else None)
                or (a.patient.phone if a.patient else "Paciente"),
                "service": a.service,
                "date": a.date.isoformat(),
                "status": str(a.status),
                "source": a.source,
            }
            for a in recent
        ],
        "usage": await usage_summary(tenant.id, str(tenant.plan)),
    }
