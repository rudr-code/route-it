from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, time
from typing import Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SECRET_KEY = os.environ.get("ROUTEIT_SECRET_KEY", "routeit-sih2026-quantum-fleet-secret-key-998877")
OTP_SECRET = os.environ.get("ROUTEIT_OTP_SECRET", "routeit-sih2026-otp-hmac-secret-key-112233")
TOKEN_TTL_SECONDS = 86400 * 7
OTP_TTL_SECONDS = 86400
MAX_OTP_ATTEMPTS = 5

bearer_scheme = HTTPBearer(auto_error=False)

def hash_password(password: str, salt: str | None = None) -> str:
    salt_val = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_val.encode("utf-8"), 100_000)
    return f"{salt_val}${dk.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    if "$" not in stored_hash:
        return False
    salt_val, _ = stored_hash.split("$", 1)
    candidate = hash_password(password, salt=salt_val)
    return hmac.compare_digest(candidate, stored_hash)

def create_access_token(user_id: str, username: str, role: str, driver_id: str | None = None) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "driver_id": driver_id,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload_b64, sig = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Invalid token signature")
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}") from exc

def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict[str, Any]:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return decode_access_token(creds.credentials)

def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user

def generate_tracking_token() -> str:
    return secrets.token_urlsafe(24)

def generate_six_digit_otp() -> str:
    return f"{secrets.randbelow(900_000) + 100_000:06d}"

def compute_otp_hmac(delivery_id: str, otp_code: str) -> str:
    msg = f"{delivery_id}:{otp_code.strip()}".encode("utf-8")
    return hmac.new(OTP_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def verify_otp_hmac(delivery_id: str, candidate_otp: str, stored_hmac: str) -> bool:
    candidate_hmac = compute_otp_hmac(delivery_id, candidate_otp)
    return hmac.compare_digest(candidate_hmac, stored_hmac)

def encrypt_customer_otp_for_portal(delivery_id: str, otp_code: str) -> str:
    key_stream = hashlib.sha256(f"{OTP_SECRET}:portal:{delivery_id}".encode("utf-8")).digest()
    otp_bytes = otp_code.encode("utf-8")
    enc = bytes(b ^ key_stream[i] for i, b in enumerate(otp_bytes))
    return base64.urlsafe_b64encode(enc).decode("utf-8")

def decrypt_customer_otp_for_portal(delivery_id: str, cipher_b64: str) -> str:
    key_stream = hashlib.sha256(f"{OTP_SECRET}:portal:{delivery_id}".encode("utf-8")).digest()
    enc = base64.urlsafe_b64decode(cipher_b64.encode("utf-8"))
    dec = bytes(b ^ key_stream[i] for i, b in enumerate(enc))
    return dec.decode("utf-8")
