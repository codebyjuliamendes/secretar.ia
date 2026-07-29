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
        tenant = await db.tenant.find_unique(
            where={"id": tenantId},
            include={
                "appointments": {
                    "include": {
                        "patient": True
                    },
                    "take": 5
                    # Ordenação pode ser feita em Python se não for suportada de forma simples
                },
                "patients": True
            }
        )
        if not tenant:
            raise HTTPException(status_code=404, detail="Clinic not found")

        # Conta alertas humanos/handoffs
        human_logs = await db.log.count(
            where={
                "tenantId": tenantId,
                "level": "HUMANO"
            }
        )

        # Ordena em Python (mais recente primeiro)
        sorted_appointments = sorted(
            tenant.appointments or [], 
            key=lambda x: x.createdAt, 
            reverse=True
        )[:5]

        recent_appointments = []
        for app in sorted_appointments:
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
                "patientCount": len(tenant.patients) if tenant.patients else 0,
                "appointmentCount": len(tenant.appointments) if tenant.appointments else 0,
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
