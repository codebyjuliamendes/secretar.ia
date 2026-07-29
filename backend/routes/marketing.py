import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Header
from db import db

router = APIRouter()

# Cron Job endpoint de marketing de retenção
@router.get("/upsell")
async def marketing_upsell(authorization: str = Header(...)):
    # Valida o token de segurança do CRON
    cron_secret = os.getenv("CRON_SECRET")
    if authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Calcula a data de exatamente 5 meses atrás
        five_months_ago = datetime.utcnow() - timedelta(days=150) # Aprox. 5 meses (150 dias)
        
        # Cria a janela de 24 horas daquele dia
        start_of_day = five_months_ago.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = five_months_ago.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Busca agendamentos antigos de Botox que foram concluídos/realizados
        appointments = await db.appointment.find_many(
            where={
                "date": {
                    "gte": start_of_day,
                    "lte": end_of_day
                },
                "status": "REALIZADO",
                "service": {
                    "contains": "Toxina" # Exemplo: Toxina Botulínica (Botox)
                }
            },
            include={
                "patient": True,
                "tenant": True
            }
        )

        # Monta payload amigável para envio de automação via N8n / WhatsApp
        targets = []
        for app in appointments:
            if app.patient:
                targets.append({
                    "tenantId": app.tenantId,
                    "clinicName": app.tenant.name if app.tenant else "Clínica",
                    "patientName": app.patient.name,
                    "patientPhone": app.patient.phone,
                    "lastService": app.service,
                    "date": app.date.isoformat()
                })

        return {
            "success": True,
            "targetCount": len(targets),
            "targets": targets
        }
        
    except Exception as e:
        print(f"[MARKETING ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail="Marketing campaign analysis failed")
