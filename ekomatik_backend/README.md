# EkoMatik Backend

FastAPI + PostgreSQL backend prototype for an IoT cigarette-butt collection/recycling system.

## Project structure

```text
app/
  api/routes.py             # REST endpoints
  core/config.py            # environment configuration
  db/session.py             # SQLAlchemy engine/session/Base
  models/models.py          # PostgreSQL ORM models
  schemas/schemas.py        # Pydantic request/response models
  services/transaction_service.py
  middleware/iot_hmac.py    # HMAC + replay protection
  utils/security.py         # HMAC/JWT helpers
  utils/create_mock_jwt.py  # development JWT generator
  main.py
```

## Run locally

1. Start PostgreSQL:

```bash
docker compose up -d postgres
```

2. Create a virtual environment and install requirements:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and change the secrets.

4. Start the API:

```bash
uvicorn app.main:app --reload
```

Swagger UI: `http://127.0.0.1:8000/docs`

## HMAC rule for the IoT endpoint

The device must send:

```text
Authorization: Bearer <hex HMAC-SHA256>
```

The signature is calculated over a **canonical string**, not the raw JSON body,
so that it matches exactly what the Deneyap Kart firmware signs
(see `ekomatik_deneyap.ino` -> `calculateHMAC()`):

```python
canonical_message = f"{rfid_uid}{amount:.2f}{timestamp}"
hmac.new(HMAC_SECRET_KEY.encode(), canonical_message.encode(), hashlib.sha256).hexdigest()
```

The JSON `timestamp` must be within ±10 seconds of server time. Requests outside the window are rejected with HTTP 401.

## Example IoT payload

```json
{
  "rfid_uid": "A1B2C3D4",
  "amount": 1.54,
  "timestamp": 1725464503
}
```

## Important production notes

- Replace startup `create_all()` with Alembic migrations.
- Replace mock JWT validation with a real identity provider.
- Use separate, long random secrets stored in a secret manager.
- Consider adding an idempotency key/device transaction UUID so a legitimately duplicated request cannot double-credit within the 10-second window.
- Add rate limiting, TLS, device registration, structured audit logging, and monitoring.