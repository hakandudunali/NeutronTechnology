# EkoMatik Flutter Client

Bu örnek Flutter uygulaması Riverpod/Provider kullanmadan, anlaşılır bir üç katmanlı yapı kullanır:

```text
HomeView (StatefulWidget)
        |
        v
EkomatikRepository
        |
        v
ApiService (http)
        |
        v
FastAPI Backend
```

## Klasörler

- `lib/services/api_service.dart`: HTTP çağrıları, JWT header, JSON ve HTTP hata yönetimi.
- `lib/services/api_exception.dart`: UI'nin yakalayabileceği tipli API hatası.
- `lib/repositories/ekomatik_repository.dart`: UI ile HTTP katmanı arasındaki soyutlama.
- `lib/models/`: API response modelleri.
- `lib/views/home_view.dart`: Bakiye, kart ekleme ve TEMA bağışı ekran akışı.
- `lib/widgets/balance_card.dart`: Yeniden kullanılabilir bakiye bileşeni.
- `lib/main.dart`: dependency composition ve uygulama başlangıcı.

## Kurulum

```bash
flutter pub get
flutter run
```

`lib/main.dart` içinde:

```dart
const String backendBaseUrl = 'http://10.0.2.2:8000';
const String mockJwt = 'REPLACE_WITH_MOCK_JWT';
```

değerlerini kendi ortamına göre değiştir.

Gerçek cihazda `10.0.2.2` yerine Raspberry Pi/FastAPI sunucusunun LAN IP adresini kullan.

## Backend kontratı

Flutter aşağıdaki endpoint'leri kullanır:

### Kart bağlama

`POST /api/v1/cards/link`

```json
{
  "rfid_uid": "A1B2C3D4"
}
```

Header:

```text
Authorization: Bearer <JWT>
```

### Harcama / bağış

`POST /api/v1/transactions/spend`

Alan adları backend'in `SpendRequest` şemasıyla (schemas.py) birebir eşleşir:

```json
{
  "amount": 5.0,
  "partner_id": "TEMA",
  "type": "DONATE_STK"
}
```

Header:

```text
Authorization: Bearer <JWT>
```

Örnek başarılı response (backend `SpendResponse` şemasıyla birebir eşleşir):

```json
{
  "status": "success",
  "transaction_id": "b3f1c2...",
  "user_id": "a9e0d4...",
  "new_balance": 12.35
}
```

### Bakiye

HomeView'un açılışta ve bağıştan sonra bakiyeyi okuyabilmesi için:

`GET /api/v1/users/me`

Örnek response:

```json
{
  "user_id": "a9e0d4...",
  "full_name": "Ada Lovelace",
  "email": "ada@example.com",
  "total_balance": 17.35
}
```

Bu endpoint backend'de tanımlıdır (`app/api/routes.py` -> `get_current_user`).

## HTTP hata davranışı

- `400`: yetersiz bakiye / geçersiz işlem
- `401`: JWT doğrulama hatası
- `403`: yetki hatası
- `404`: kaynak bulunamadı
- `409`: kart zaten ekli
- `422`: validation hatası
- `500`: backend hatası

Bu kodlar `ApiException` üzerinden HomeView'da Snackbar'a dönüştürülür.

## Güvenlik notu

Mock JWT doğrudan `main.dart` içinde gösterilmiştir çünkü bu proje bir mimari örnektir. Gerçek uygulamada token secure storage içinde tutulmalı ve login/refresh mekanizması kullanılmalıdır.