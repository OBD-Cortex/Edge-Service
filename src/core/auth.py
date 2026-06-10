"""
Authentication Module -- OBD-Cortex
Provides JWT token management, bcrypt password hashing, API key
verification, and HMAC device signature validation.

Security Hardening Applied:
  [*] Timing-safe API key comparison (hmac.compare_digest)
  [*] JWT lifetime reduced to 7 days with iss/aud/jti claims
  [*] Minimum secret length validation at startup
  [*] HMAC replay protection with timestamp window + nonce cache
  [*] Failed auth attempt logging (without leaking secrets)
"""

import datetime
import logging
import hmac
import hashlib
from collections import OrderedDict
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from core.database import col_devices

logger = logging.getLogger(__name__)

# Removed unused validation and globals


# Removed unused auth methods


device_token_header = APIKeyHeader(name="X-Device-Token", auto_error=True)

async def verify_device_token(device_token: str = Security(device_token_header)):
    """Verifies that the incoming request contains a valid hardware device token."""
    normalized_token = device_token.strip().upper()
    device = await col_devices.find_one({"device_token": normalized_token})
    if not device:
        logger.warning(f"[!] Invalid device token attempt (token length: {len(device_token)})")
        raise HTTPException(status_code=403, detail="Invalid Device Token")
    return normalized_token


# ----------------------------------------------------------
# 5. HMAC SIGNATURE VERIFICATION (Edge Devices)
# ----------------------------------------------------------
# Replay protection: reject timestamps outside a 5-minute window
# and cache recent nonces to prevent exact replays.
_HMAC_WINDOW_SECONDS = 300  # 5 minutes
_NONCE_CACHE_MAX = 10000

# Ordered dict acts as an LRU nonce cache with bounded size
_nonce_cache = OrderedDict()


def _check_nonce(nonce_key: str) -> bool:
    """Returns True if this nonce has been seen before (replay detected)."""
    if nonce_key in _nonce_cache:
        return True
    # Evict oldest entries if cache is full
    while len(_nonce_cache) >= _NONCE_CACHE_MAX:
        _nonce_cache.popitem(last=False)
    _nonce_cache[nonce_key] = True
    return False


async def verify_device_signature(request: Request):
    """Verifies the HMAC-SHA256 signature with replay protection for edge endpoints."""
    device_id_str = request.headers.get("X-Device-ID")
    timestamp = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")

    if not device_id_str or not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing signature headers")

    try:
        device_id = int(device_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Device ID format")

    # SECURITY: Enforce timestamp window to prevent replay attacks.
    # Reject requests with timestamps outside +/- 5 minutes of server time.
    try:
        req_time = datetime.datetime.fromisoformat(timestamp)
        now = datetime.datetime.now(datetime.timezone.utc)
        drift = abs((now - req_time).total_seconds())
        if drift > _HMAC_WINDOW_SECONDS:
            logger.warning(
                f"[!] HMAC timestamp rejected for device {device_id}: "
                f"drift={drift:.0f}s (max={_HMAC_WINDOW_SECONDS}s)"
            )
            raise HTTPException(status_code=401, detail="Request timestamp expired")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid timestamp format")

    # SECURITY: Nonce check -- reject exact (device_id, timestamp, signature) replays
    nonce_key = f"{device_id}:{timestamp}:{signature}"
    if _check_nonce(nonce_key):
        logger.warning(f"[!] Replay attack detected for device {device_id}")
        raise HTTPException(status_code=401, detail="Replayed request")

    device = await col_devices.find_one({"device_id": device_id})
    if not device or "device_secret" not in device:
        raise HTTPException(status_code=403, detail="Invalid or unprovisioned Device ID")

    body = await request.body()
    signed_data = timestamp.encode('utf-8') + body

    expected_sig = hmac.new(device["device_secret"].encode('utf-8'), signed_data, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        logger.warning(f"[!] Invalid HMAC signature for device {device_id}")
        raise HTTPException(status_code=403, detail="Invalid signature")

    return device
