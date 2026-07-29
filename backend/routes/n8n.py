import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from db import db

router = APIRouter()

# Dependência para validar a chave de API
async def verify_api_key(x_api_key: str = Header(..., alias="x-api-key")):
    if x_api_key != os.getenv("SAAS_API_KEY"):
        raise HTTPException(status_code=401, detail="Unauthorized API Key")

# Modelos Pydantic para validação de dados
class PatientUpsert(BaseModel):
    tenantId: str
    phone: str
    name: Optional[str] = None

class AppointmentCreate(BaseModel):
    tenantId: str
    phone: str
    service: str
    date: datetime # Espera formato ISO 8601

class AlertCreate(BaseModel):
    tenantId: str
    phone: str
    context: str

# Endpoints de Integração com N8n

@router.get("/config")
async def get_config(tenantId: str, _ = Depends(verify_api_key)):
    tenant = await db.tenant.find_unique(where={"id": tenantId})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Bloqueia se a assinatura estiver inadimplente
    if tenant.status == "PAST_DUE":
        raise HTTPException(status_code=402, detail="Subscription past due. Bot disabled.")
        
    return {
        "id": tenant.id,
        "name": tenant.name,
        "whatsapp": tenant.whatsapp,
        "prompt": tenant.prompt,
        "prices": tenant.prices,
        "businessHours": tenant.businessHours
    }

@router.post("/patients")
async def upsert_patient(data: PatientUpsert, _ = Depends(verify_api_key)):
    try:
        # Usa o unique index composto do Prisma para fazer o Upsert
        patient = await db.patient.upsert(
            where={
                "tenantId_phone": {
                    "tenantId": data.tenantId,
                    "phone": data.phone
                }
            },
            data={
                "create": {
                    "tenantId": data.tenantId,
                    "phone": data.phone,
                    "name": data.name
                },
                "update": {
                    "name": data.name if data.name else ""
                }
            }
        )
        return {"success": True, "patient": patient}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/appointments")
async def create_appointment(data: AppointmentCreate, _ = Depends(verify_api_key)):
    try:
        # Garante que o paciente existe no banco
        patient = await db.patient.upsert(
            where={
                "tenantId_phone": {
                    "tenantId": data.tenantId,
                    "phone": data.phone
                }
            },
            data={
                "create": {
                    "tenantId": data.tenantId,
                    "phone": data.phone
                },
                "update": {}
            }
        )

        # Cria o agendamento associado
        appointment = await db.appointment.create(
            data={
                "tenantId": data.tenantId,
                "patientId": patient.id,
                "service": data.service,
                "date": data.date,
                "status": "PENDENTE"
            }
        )
        return {"success": True, "appointment": appointment}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/alerts")
async def handoff_alert(data: AlertCreate, _ = Depends(verify_api_key)):
    try:
        # Registra o Handoff Humano como log crítico no banco
        await db.log.create(
            data={
                "tenantId": data.tenantId,
                "level": "HUMANO",
                "message": f"Handoff acionado para o telefone {data.phone}. Contexto: {data.context}"
            }
        )
        
        # Log no console para simular Webhook / WebSocket Realtime
        print(f"[ALERT REALTIME] Handoff humano na clínica {data.tenantId} para o paciente {data.phone}")
        return {"success": True, "delivered": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
