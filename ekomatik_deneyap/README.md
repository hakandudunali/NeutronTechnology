# EkoMatik Deneyap Kart Firmware

Arduino IDE / C++ firmware for the EkoMatik main controller.

## Ana akış

`IDLE -> WAIT_ITEM -> WAIT_ML -> WEIGHING -> SYNC -> API -> FINISH -> IDLE`

## Gerekli kütüphaneler

Arduino IDE Library Manager üzerinden:

- MFRC522
- LiquidCrystal_I2C
- HX711
- ESP32Servo
- ArduinoJson

WiFi, HTTPClient, WiFiClientSecure, SPI, Wire ve mbedTLS ESP32 Arduino/Deneyap core ile gelir.

Deneyap'ın resmi Arduino core deposunda `Deneyap Kart 1A` desteği bulunur. Arduino IDE'de Deneyap geliştirme kartları core'u kurulmalıdır.

## Kritik entegrasyon notu: HMAC

Firmware, kullanıcının istediği şekilde şu metni imzalar:

```text
<rfid_uid><puan><timestamp>
```

Örneğin puan `1.54` ise:

```text
A1B2C3D41.541725464503
```

HMAC-SHA256 secret ile hesaplanır ve hex olarak:

```http
Authorization: Bearer <64-hex-character-signature>
```

şeklinde gönderilir.

### Backend uyumluluğu

`ekomatik_backend/app/middleware/iot_hmac.py` bu firmware ile aynı canonical
string'i üretip doğrular (raw JSON body değil):

```python
message = f"{payload['rfid_uid']}{payload['amount']:.2f}{payload['timestamp']}"
expected = hmac.new(
    SECRET_KEY.encode(),
    message.encode(),
    hashlib.sha256,
).hexdigest()
```

Firmware ile backend imza yöntemi birebir eşleşir; ek bir değişikliğe gerek yoktur.

## Pin notu

Kod, kullanıcı tarafından verilen GPIO değerlerini temel alır. Ancak özellikle Deneyap Kart 1A'nın gerçek kart revizyonunun SPI/I2C/UART pin eşleşmesi fiziksel kart üzerindeki pin isimleriyle kontrol edilmelidir. SPI SCK/MISO/MOSI pinleri kodda ayrı sabitler olarak bırakılmıştır.

## Güvenlik

`secureClient.setInsecure()` yalnızca prototip/yerel geliştirme içindir. Üretimde backend CA sertifikası `setCACert()` ile doğrulanmalıdır.

`SECRET_KEY`, Wi-Fi kimlik bilgileri ve backend URL'si de üretim firmware'inde kaynak koda açık şekilde gömülmemelidir.

## Fiziksel pin uyumlulugu uyarısı

Deneyap Kart 1A'nın resmi dokümanında SPI hattı D4/D5/D6/D7, I2C ise SDA=D10 ve SCL=D11 olarak tanımlanır; UART TX/RX de D2/D3'tür. Bu firmware ise kullanıcının verdiği SS=5, RST=22, servo=18 ve UART2 RX=16/TX=17 gereksinimlerini temel alır. Bu nedenle SPI'nin verilmemiş SCK/MISO/MOSI pinleri kodda ayrı sabitler olarak bırakılmıştır ve servo GPIO18 ile çakışmayacak şekilde örneklenmiştir. Fiziksel montajda kart revizyonunun pinout'u mutlaka doğrulanmalıdır.