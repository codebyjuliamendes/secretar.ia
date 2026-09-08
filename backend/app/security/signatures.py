"""Verificação de assinaturas HMAC de webhooks (Meta/WhatsApp e Stripe)."""

from __future__ import annotations

import hashlib
import hmac
import time


def verify_hub_signature(body: bytes, header_value: str | None, secret: str) -> bool:
    """Formato Meta: `X-Hub-Signature-256: sha256=<hex>`."""
    if not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header_value[len("sha256=") :], expected)


def sign_hub(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_stripe_signature(body: bytes, header_value: str | None, secret: str, tolerance_seconds: int = 300) -> bool:
    """Formato Stripe: `Stripe-Signature: t=<ts>,v1=<hex>[,v1=...]`."""
    if not header_value:
        return False
    parts = dict(p.split("=", 1) for p in header_value.split(",") if "=" in p)
    ts = parts.get("t")
    if not ts or not ts.isdigit():
        return False
    if abs(time.time() - int(ts)) > tolerance_seconds:
        return False
    signed = f"{ts}.".encode() + body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    candidates = [v.split("=", 1)[1] for v in header_value.split(",") if v.startswith("v1=")]
    return any(hmac.compare_digest(c, expected) for c in candidates)


def sign_stripe(body: bytes, secret: str, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode("utf-8"), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"
