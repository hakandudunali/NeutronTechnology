# EkoMatik Backend

IoT sigara izmariti toplama/geri dönüşüm sistemi için FastAPI + PostgreSQL backend prototipi.

## Proje yapısı

```text
app/
  api/routes.py             # REST uç noktaları
  core/config.py            # Ortam (environment) yapılandırması
  db/session.py             # SQLAlchemy engine/session/Base
  models/models.py          # PostgreSQL ORM modelleri
  schemas/schemas.py        # Pydantic istek/yanıt modelleri
  services/transaction_service.py
  middleware/iot_hmac.py    # HMAC + tekrarlama (replay) koruması
  utils/security.py         # HMAC/JWT yardımcı işlevleri
  utils/create_mock_jwt.py  # Geliştirme aşaması için JWT oluşturucu
  main.py

```

## Yerel ortamda çalıştırma

1. PostgreSQL'i başlatın:

```bash
docker compose up -d postgres

```

2. Bir sanal ortam (virtual environment) oluşturun ve gereksinimleri yükleyin:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

```

3. `.env.example` dosyasını kopyalayarak `.env` olarak adlandırın ve gizli anahtarları (secrets) değiştirin.
4. API'yi başlatın:

```bash
uvicorn app.main:app --reload

```

Swagger UI: `[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)`

## IoT uç noktası için HMAC kuralı

Cihaz şunları göndermelidir:

```text
Authorization: Bearer <hex HMAC-SHA256>

```

İmza, ham JSON gövdesi üzerinden değil, Deneyap Kart donanım yazılımının (firmware) imzaladığı ile tam olarak eşleşmesi için **kanonik bir dize (canonical string)** üzerinden hesaplanır
(bkz. `ekomatik_deneyap.ino` -> `calculateHMAC()`):

```python
canonical_message = f"{rfid_uid}{amount:.2f}{timestamp}"
hmac.new(HMAC_SECRET_KEY.encode(), canonical_message.encode(), hashlib.sha256).hexdigest()

```

JSON içindeki `timestamp` değeri sunucu saatinin ±10 saniye aralığında olmalıdır. Bu zaman penceresinin dışındaki istekler HTTP 401 ile reddedilir.

## Örnek IoT veri yükü (payload)

```json
{
  "rfid_uid": "A1B2C3D4",
  "amount": 1.54,
  "timestamp": 1725464503
}

```

## Önemli üretim (production) notları

* Başlangıçtaki `create_all()` işlevini Alembic migrasyonları (migrations) ile değiştirin.
* Sahte (mock) JWT doğrulamasını gerçek bir kimlik sağlayıcı (identity provider) ile değiştirin.
* Bir sır yöneticisinde (secret manager) saklanan ayrı, uzun ve rastgele gizli anahtarlar kullanın.
* 10 saniyelik zaman penceresi içinde meşru bir şekilde yinelenen isteğin çifte bakiye yüklemesi (double-credit) yapmasını önlemek için, bir eşkuvvetlilik anahtarı (idempotency key) / cihaz işlem UUID'si eklemeyi düşünün.
* Hız sınırlaması (rate limiting), TLS, cihaz kaydı, yapılandırılmış denetim günlüğü (structured audit logging) ve izleme (monitoring) ekleyin.
