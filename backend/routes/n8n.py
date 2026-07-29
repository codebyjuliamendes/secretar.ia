import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends, Request
from pydantic import BaseModel
from db import db
from core.security import verify_whatsapp_signature
from core.router import rotear_conversa
from core.queue import send_job

router = APIRouter()

# Dependência para validar a chave de API (para rotas de controle interno)
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
    date: datetime

class AlertCreate(BaseModel):
    tenantId: str
    phone: str
    context: str

# Payload do Webhook do WhatsApp (Evolution API / Meta Webhook)
class WhatsAppWebhook(BaseModel):
    messageId: str
    phone: str
    text: str
    tenantId: str # Identifica a qual clínica esse WhatsApp pertence

# -------------------------------------------------------------
# WEBHOOK RECEIVER PRINCIPAL (SUBSTITUI O CORE DO N8N)
# -------------------------------------------------------------

@router.post("/webhook")
async def whatsapp_webhook(
    data: WhatsAppWebhook,
    request: Request,
    _ = Depends(verify_whatsapp_signature) # Pilar 8: Validação Criptográfica da Assinatura
):
    # 1. Pilar 3: Idempotência (Evita duplicidade por reenvio da Meta)
    try:
        await db.processedmessage.create(
            data={"messageId": data.messageId}
        )
    except Exception as e:
        # Se falhar a gravação da chave única, significa que a mensagem já foi processada
        print(f"[IDEMPOTENCY] Mensagem duplicada ignorada (ID: {data.messageId})")
        return {"success": True, "status": "duplicate_ignored"}

    # 2. Pilar 5: Configuração por Cliente (Tenant)
    tenant = await db.tenant.find_unique(where={"id": data.tenantId})
    if not tenant:
        raise HTTPException(status_code=404, detail="Clinic (Tenant) not found")

    # Bloqueia se a mensalidade estiver atrasada (Billing Status)
    if tenant.status == "PAST_DUE":
        print(f"[BILLING BLOCK] Clínica {tenant.name} tentou receber mensagem mas está bloqueada.")
        return {"success": False, "status": "blocked_due_to_billing"}

    # 3. Classificação de Intenções (Heurística Local para Testes / Plug & Play com LLM)
    # Em produção, você substituiria esta regra por uma chamada para o Gemini/Claude
    text_lower = data.text.lower()
    if "marcar" in text_lower or "agendar" in text_lower or "botox" in text_lower:
        intent = "AGENDAR"
    elif "cancelar" in text_lower or "desmarcar" in text_lower:
        intent = "CANCELAR"
    elif "funcionamento" in text_lower or "preço" in text_lower or "valor" in text_lower:
        intent = "INFO"
    elif "ajuda" in text_lower or "atendente" in text_lower or "falar com humano" in text_lower:
        intent = "HUMANO"
    else:
        intent = "INFO" # Default para responder dúvidas genéricas

    # 4. Pilar 1 & 6: Roteamento de Conversa (Switch) com Fallback Humano e Logs
    response_text = await rotear_conversa(intent, data.phone, data.tenantId, data.text)

    # 5. Pilar 2: Enfileiramento de Resposta via Database Queue (Resiliência Meta)
    await send_job("enviar-whatsapp", {
        "phone": data.phone,
        "message": response_text
    })

    return {
        "success": True,
        "status": "processed",
        "intent": intent,
        "response": response_text
    }

# -------------------------------------------------------------
# ENDPOINTS AUXILIARES (SUPORTE INTERNO / LEGACY REST API)
# -------------------------------------------------------------

@router.get("/config")
async def get_config(tenantId: str, _ = Depends(verify_api_key)):
    tenant = await db.tenant.find_unique(where={"id": tenantId})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@router.post("/patients")
async def upsert_patient(data: PatientUpsert, _ = Depends(verify_api_key)):
    patient = await db.patient.upsert(
        where={"tenantId_phone": {"tenantId": data.tenantId, "phone": data.phone}},
        data={
            "create": {"tenantId": data.tenantId, "phone": data.phone, "name": data.name},
            "update": {"name": data.name if data.name else ""}
        }
    )
    return {"success": True, "patient": patient}

@router.post("/appointments")
async def create_appointment(data: AppointmentCreate, _ = Depends(verify_api_key)):
    patient = await db.patient.upsert(
        where={"tenantId_phone": {"tenantId": data.tenantId, "phone": data.phone}},
        data={
            "create": {"tenantId": data.tenantId, "phone": data.phone},
            "update": {}
        }
    )
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
