# EkoMatik Raspberry Pi Zero Edge Agent

Raspberry Pi Zero ile Deneyap Kart 1A arasında UART haberleşmesi yapar ve kameradan alınan fotoğrafı EkoMatik FastAPI backend'inin vision endpoint'ine gönderir.

## Kurulum

```bash
python3 -m pip install -r requirements.txt
```

Picamera2 kullanıyorsanız Raspberry Pi OS üzerinde ayrıca:

```bash
sudo apt update
sudo apt install python3-picamera2
```

OpenCV kamera fallback'i için kamera cihazının sistem tarafından görüldüğünden emin olun.

## Çalıştırma

```bash
export EKOMATIK_UART_PORT=/dev/serial0
export EKOMATIK_BACKEND_URL=http://192.168.1.100:8000/api/v1/vision/analyze
python3 edge_agent.py
```

Varsayılan UART baudrate: `115200`.

## UART protokolü

Deneyap Kart:

```text
FOTOGRAF_CEK\n
```

Edge Agent başarılı izmarit tespitinde:

```text
ONAY\n
```

İzmarit değilse veya kamera/ağ/backend hatası olursa:

```text
RED\n
```

## JPEG davranışı

Frame merkezden kare kırpılır ve 320x320 yapılır. JPEG kalitesi 90'dan aşağı doğru düşürülerek 50 KB sınırı aranır. Çok karmaşık görüntülerde son çare olarak grayscale JPEG denenir.

## Backend ile uyumluluk

Önceki FastAPI backend'inde endpoint:

`POST /api/v1/vision/analyze`

ve multipart alan adı:

`file`

olarak tanımlandığından script doğrudan:

```python
files = {"file": ("capture.jpg", image_stream, "image/jpeg")}
```

gönderir.