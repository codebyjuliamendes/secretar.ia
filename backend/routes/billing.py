from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from db import db

router = APIRouter()

# Webhook do Gateway de Pagamento (Stripe/Asaas)
@router.post("/billing")
async def billing_webhook(request: Request):
    try:
        payload = await request.json()
        event_type = payload.get("type")
        data_obj = payload.get("data", {})
        obj = data_obj.get("object", {})
        
        # Pega o ID da Assinatura
        subscription_id = obj.get("id") or payload.get("id")
        
        if not subscription_id:
            raise HTTPException(status_code=400, detail="Subscription ID not found in payload")

        # Se o pagamento falhar ou for cancelado
        if event_type in ["invoice.payment_failed", "customer.subscription.deleted"]:
            # Usando update_many no Prisma Python
            updated = await db.tenant.update_many(
                where={"subscriptionId": subscription_id},
                data={"status": "PAST_DUE"}
            )
            print(f"[BILLING] Assinatura {subscription_id} bloqueada por inadimplência. Afetou {updated} registros.")

        # Se o pagamento for bem sucedido
        elif event_type in ["invoice.payment_succeeded", "customer.subscription.created"]:
            updated = await db.tenant.update_many(
                where={"subscriptionId": subscription_id},
                data={"status": "ACTIVE"}
            )
            print(f"[BILLING] Assinatura {subscription_id} confirmada. Acesso liberado para {updated} registros.")

        return {"received": True}
        
    except Exception as e:
        print(f"[BILLING ERROR] {str(e)}")
        raise HTTPException(status_code=400, detail="Webhook handler failed")
