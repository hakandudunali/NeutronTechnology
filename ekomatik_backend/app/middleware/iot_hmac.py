"""Middleware that authenticates and freshness-checks IoT transaction requests."""

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.utils.security import verify_hmac_signature, verify_timestamp


class IoTHMACMiddleware(BaseHTTPMiddleware):
    """Protect the IoT transaction endpoint with HMAC and replay protection.

    Only `POST /api/v1/transactions/add` is intercepted. The complete request body
    is cached by Starlette, checked against the HMAC Authorization header, parsed for
    its Unix timestamp, and then passed onward to the route after successful validation.
    """

    protected_path = "/api/v1/transactions/add"

    async def dispatch(self, request: Request, call_next):
        """Validate the request before allowing the route handler to execute."""

        if request.method == "POST" and request.url.path == self.protected_path:
            raw_body = await request.body()
            authorization = request.headers.get("Authorization", "")

            # 1. ADIM: Önce JSON verisini parse et (Ayrıştır)
            try:
                payload = json.loads(raw_body)
                rfid_uid = str(payload["rfid_uid"])
                amount = float(payload["amount"])
                timestamp = int(payload["timestamp"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid or missing JSON payload fields"},
                )

            # 2. ADIM: Deneyap Kart'ın oluşturduğu C++ string formatını birebir kurgula
            # C++ Formatı: <rfid_uid><amount_2_ondalik><timestamp>
            canonical_message = f"{rfid_uid}{amount:.2f}{timestamp}"

            # 3. ADIM: canonical_message'ı kontrol et (raw_body değil)
            if not verify_hmac_signature(canonical_message.encode("utf-8"), authorization):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid HMAC signature"},
                )

            if not verify_timestamp(timestamp):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Replay Attack: timestamp is outside the 10-second window"},
                )

        return await call_next(request)