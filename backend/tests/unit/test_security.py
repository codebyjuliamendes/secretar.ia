import time

from app.security.passwords import hash_password, validate_password_policy, verify_password
from app.security.ratelimit import SlidingWindowRateLimiter
from app.security.signatures import sign_hub, sign_stripe, verify_hub_signature, verify_stripe_signature
from app.security.tokens import create_access_token, decode_access_token, generate_opaque_token, hash_token

SECRET = "unit-test-secret-unit-test-secret-0123456789"


def test_password_roundtrip_and_policy():
    h = hash_password("Senha1234")
    assert h.startswith("$2b$")
    assert verify_password("Senha1234", h)
    assert not verify_password("outra", h)
    assert not verify_password("x", "hash-invalido")
    assert validate_password_policy("curta") is not None
    assert validate_password_policy("12345678") is not None
    assert validate_password_policy("abcdefgh") is not None
    assert validate_password_policy("Senha1234") is None


def test_access_token_roundtrip_and_tamper():
    tok = create_access_token(user_id="u1", platform_role="USER", secret=SECRET, minutes=5)
    payload = decode_access_token(tok, SECRET)
    assert payload and payload["sub"] == "u1" and payload["prl"] == "USER"
    assert decode_access_token(tok, "wrong-secret-wrong-secret-wrong-secret-000") is None
    assert decode_access_token(tok + "x", SECRET) is None
    expired = create_access_token(user_id="u1", platform_role="USER", secret=SECRET, minutes=-1)
    assert decode_access_token(expired, SECRET) is None


def test_opaque_tokens_are_hashed_unique():
    a, b = generate_opaque_token(), generate_opaque_token()
    assert a != b and len(a) > 40
    assert hash_token(a) != hash_token(b) and len(hash_token(a)) == 64


def test_hub_signature():
    body = b'{"messageId":"1"}'
    sig = sign_hub(body, "s3cret")
    assert verify_hub_signature(body, sig, "s3cret")
    assert not verify_hub_signature(body + b" ", sig, "s3cret")
    assert not verify_hub_signature(body, sig, "other")
    assert not verify_hub_signature(body, None, "s3cret")
    assert not verify_hub_signature(body, "md5=abc", "s3cret")


def test_stripe_signature_and_tolerance():
    body = b'{"id":"evt_1","type":"invoice.paid"}'
    header = sign_stripe(body, "whsec_x")
    assert verify_stripe_signature(body, header, "whsec_x")
    assert not verify_stripe_signature(body, header, "whsec_y")
    old = sign_stripe(body, "whsec_x", ts=int(time.time()) - 3600)
    assert not verify_stripe_signature(body, old, "whsec_x")
    assert not verify_stripe_signature(body, "garbage", "whsec_x")


def test_rate_limiter():
    rl = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    assert all(rl.allow("k") for _ in range(3))
    assert not rl.allow("k")
    assert rl.allow("other")
    rl.reset()
    assert rl.allow("k")
