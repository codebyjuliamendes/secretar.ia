from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import db

router = APIRouter()

class ClinicConfigUpdate(BaseModel):
    prompt: Optional[str] = None
    prices: Optional[str] = None
    businessHours: Optional[str] = None

@router.get("/dashboard")
async def get_clinic_dashboard(tenantId: str):
    try:
        # Verifica se o tenant existe de forma rápida
        tenant_exists = await db.tenant.find_unique(where={"id": tenantId})
        if not tenant_exists:
            raise HTTPException(status_code=404, detail="Clinic not found")

        # Contagens performáticas via COUNT no Postgres, utilizando índices criados
        patient_count = await db.patient.count(where={"tenantId": tenantId})
        appointment_count = await db.appointment.count(where={"tenantId": tenantId})

        # Conta alertas de transbordo humano (otimizado por index)
        human_logs = await db.log.count(
            where={
                "tenantId": tenantId,
                "level": "HUMANO"
            }
        )

        # Busca apenas os 5 agendamentos mais recentes ordenados diretamente pelo banco
        recent_apps = await db.appointment.find_many(
            where={"tenantId": tenantId},
            include={
                "patient": True
            },
            order={
                "createdAt": "desc"
            },
            take=5
        )

        recent_appointments = []
        for app in recent_apps:
            recent_appointments.append({
                "id": app.id,
                "patientName": app.patient.name if app.patient and app.patient.name else "Paciente",
                "service": app.service,
                "date": app.date.isoformat(),
                "status": app.status
            })

        return {
            "success": True,
            "metrics": {
                "patientCount": patient_count,
                "appointmentCount": appointment_count,
                "humanHandoffs": human_logs
            },
            "recentAppointments": recent_appointments
        }
    except Exception as e:
        print(f"[CLINIC ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/config")
async def update_clinic_config(tenantId: str, data: ClinicConfigUpdate):
    try:
        update_data = {}
        if data.prompt is not None:
            update_data["prompt"] = data.prompt
        if data.prices is not None:
            update_data["prices"] = data.prices
        if data.businessHours is not None:
            update_data["businessHours"] = data.businessHours

        tenant = await db.tenant.update(
            where={"id": tenantId},
            data=update_data
        )
        return {"success": True, "tenant": tenant}
    except Exception as e:
        print(f"[CLINIC ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
