import hmac
import hashlib
import os
from fastapi import Request, HTTPException, Header
from typing import Optional

APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")

async def verify_whatsapp_signature(request: Request, x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256")):
    """
    Valida a assinatura SHA-256 enviada pela Meta nos webhooks do WhatsApp.
    Garante que a chamada realmente partiu dos servidores oficiais do WhatsApp.
    """
    if not APP_SECRET:
        # Se não houver segredo configurado localmente, bypassa para facilitar desenvolvimento
        print("[WARNING] WHATSAPP_APP_SECRET não configurado. Ignorando validação de assinatura.")
        return

    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Assinatura X-Hub-Signature-256 ausente.")

    if not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(status_code=400, detail="Formato de assinatura inválido.")

    # Pega o corpo bruto do webhook
    body = await request.body()
    expected_signature = x_hub_signature_256.split("sha256=")[1]

    # Calcula a assinatura HMAC SHA-256 baseada no corpo bruto
    h = hmac.new(APP_SECRET.encode('utf-8'), body, hashlib.sha256)
    calculated_signature = h.hexdigest()

    # Compara em tempo constante para evitar ataques de timing
    if not hmac.compare_digest(expected_signature, calculated_signature):
        print(f"[SECURITY] Assinatura inválida. Esperada: {expected_signature}, Calculada: {calculated_signature}")
        raise HTTPException(status_code=401, detail="Assinatura criptográfica inválida.")
