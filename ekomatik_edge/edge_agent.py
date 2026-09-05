#!/usr/bin/env python3
"""
EkoMatik - Raspberry Pi Zero Edge Agent

Bu script Raspberry Pi Zero üzerinde çalışır ve:
1. Deneyap Kart 1A ile UART üzerinden haberleşir.
2. FOTOGRAF_CEK komutunu alınca kameradan görüntü alır.
3. Görüntüyü merkezden kare olacak şekilde kırpar, 320x320'e resize eder.
4. JPEG görüntüyü 50 KB altında tutmaya çalışır.
5. requests.Session() kullanarak görüntüyü FastAPI backend'ine gönderir.
6. Backend sonucu is_izmarit=true ise Deneyap Kart'a ONAY, değilse RED yollar.
7. Ağ/kamera/seri port hatalarında sistemi kilitlemeden RED gönderir.

Kurulum örneği (Raspberry Pi OS):
    python3 -m pip install pyserial requests opencv-python

Picamera2 kullanacaksanız Raspberry Pi tarafında sistem paketlerini de kurmanız
gerekebilir. Script önce Picamera2'yi dener, bulunamazsa OpenCV VideoCapture'a
geçer.
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import Optional

import cv2
import requests
import serial
from serial import SerialException

# Picamera2 her cihazda kurulu olmayabilir. Bu nedenle import'u opsiyonel tutuyoruz.
try:
    from picamera2 import Picamera2  # type: ignore
except ImportError:
    Picamera2 = None  # type: ignore


# -----------------------------------------------------------------------------
# Yapılandırma
# -----------------------------------------------------------------------------

# Deneyap Kart'ın bağlandığı UART cihazı. USB-UART adaptör kullanıyorsanız
# /dev/ttyUSB0 veya /dev/ttyACM0 gibi bir değer verebilirsiniz.
UART_PORT = os.getenv("EKOMATIK_UART_PORT", "/dev/serial0")

# Kullanıcının tarif ettiği haberleşme hızı.
UART_BAUDRATE = int(os.getenv("EKOMATIK_UART_BAUDRATE", "115200"))

# Backend adresini ortam değişkeninden alıyoruz. Böylece IP değiştiğinde
# kaynak kodunu değiştirmek gerekmez.
BACKEND_URL = os.getenv(
    "EKOMATIK_BACKEND_URL",
    "http://127.0.0.1:8000/api/v1/vision/analyze",
)

# HTTP bağlantı ve response timeout değerleri saniye cinsindedir.
HTTP_CONNECT_TIMEOUT = float(os.getenv("EKOMATIK_HTTP_CONNECT_TIMEOUT", "3"))
HTTP_READ_TIMEOUT = float(os.getenv("EKOMATIK_HTTP_READ_TIMEOUT", "8"))

# Kameranın OpenCV ile açılacağı cihaz numarası.
CAMERA_INDEX = int(os.getenv("EKOMATIK_CAMERA_INDEX", "0"))

# Görüntü boyutu backend'e gönderilmeden önce tam olarak 320x320 yapılır.
IMAGE_SIZE = (320, 320)

# İstenen maksimum JPEG boyutu. 50 * 1024 = 51200 byte.
MAX_JPEG_BYTES = 50 * 1024

# Kameradan görüntü alırken maksimum bekleme süresi.
CAMERA_TIMEOUT_SECONDS = float(os.getenv("EKOMATIK_CAMERA_TIMEOUT", "5"))

# UART komutlarının sonunda kullanılacak satır sonu.
UART_LINE_END = b"\n"


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("ekomatik-edge")


class CameraCapture:
    """Kamera erişimini tek bir sınıfta yöneten edge bileşeni.

    Picamera2 mevcutsa Raspberry Pi'nin CSI kamerasını kullanır. Picamera2
    bulunamazsa OpenCV'nin VideoCapture API'sine geçer. Bu yapı sayesinde
    prototipte donanım sürücüsü değişse bile ana UART/HTTP akışı değişmez.
    """

    def __init__(self, camera_index: int = 0) -> None:
        """Kamera nesnesini oluşturur ve backend seçimini belirler.

        Args:
            camera_index: OpenCV kullanılacaksa video cihazının indeksidir.
        """
        self.camera_index = camera_index
        self._picam: Optional[object] = None
        self._opencv_camera: Optional[cv2.VideoCapture] = None

        # Picamera2 import edilebildiyse CSI kamera için onu tercih ediyoruz.
        if Picamera2 is not None:
            try:
                self._picam = Picamera2()
                config = self._picam.create_still_configuration(
                    main={"size": (640, 640), "format": "RGB888"}
                )
                self._picam.configure(config)
                self._picam.start()
                # Kameranın sensör/ISP'nin hazır hale gelmesi için kısa bir süre
                # veriyoruz. Çok uzun beklemek istemediğimiz için yaklaşık 1 sn.
                time.sleep(1.0)
                logger.info("Camera backend: Picamera2")
                return
            except Exception as exc:
                logger.warning("Picamera2 başlatılamadı, OpenCV deneniyor: %s", exc)
                self._picam = None

        # USB kamera veya OpenCV destekli başka bir kamera için fallback.
        camera = cv2.VideoCapture(self.camera_index)
        if not camera.isOpened():
            camera.release()
            raise RuntimeError("Kamera açılamadı: Picamera2 ve OpenCV başarısız.")

        # Fazla büyük görüntü taşımamak için capture çözünürlüğünü makul bir
        # değerde tutuyoruz; son 320x320 dönüşümü ayrıca uygulanacaktır.
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._opencv_camera = camera
        logger.info("Camera backend: OpenCV VideoCapture(%s)", self.camera_index)

    def capture(self) -> bytes:
        """Kameradan tek kare alır, işler ve JPEG bytes olarak döndürür.

        İşlemler sırasıyla:
        1. Ham frame alınır.
        2. Görüntü merkezden kare olacak şekilde crop edilir.
        3. 320x320 piksele resize edilir.
        4. JPEG kalite seviyesi azaltılarak 50 KB sınırı sağlanır.

        Returns:
            Sıkıştırılmış JPEG görüntü byte dizisi.

        Raises:
            RuntimeError: Kamera frame üretemezse veya JPEG encode edilemezse.
        """
        if self._picam is not None:
            # Picamera2 RGB görüntü döndürür; OpenCV işlemleri için RGB'den BGR'a
            # çeviriyoruz çünkü cv2 imencode BGR görüntüyü beklemektedir.
            frame_rgb = self._picam.capture_array()
            frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        elif self._opencv_camera is not None:
            ok, frame = self._opencv_camera.read()
            if not ok or frame is None:
                raise RuntimeError("OpenCV kameradan frame alınamadı.")
        else:
            raise RuntimeError("Kamera backend'i hazır değil.")

        processed = crop_center_square_and_resize(frame, IMAGE_SIZE)
        return encode_jpeg_under_limit(processed, MAX_JPEG_BYTES)

    def close(self) -> None:
        """Kamera kaynaklarını güvenli biçimde serbest bırakır.

        Raspberry Pi uzun süre çalışan bir edge cihazı olduğu için program
        durduğunda kamera sürücüsünün açık bırakılmasını engeller.
        """
        if self._opencv_camera is not None:
            self._opencv_camera.release()
            self._opencv_camera = None

        if self._picam is not None:
            try:
                self._picam.stop()
            except Exception:
                logger.exception("Picamera2 stop() sırasında hata oluştu.")
            self._picam = None


def crop_center_square_and_resize(frame, target_size: tuple[int, int]) -> object:
    """Frame'i merkezden kare kırpar ve hedef boyuta resize eder.

    Kare crop yapılmasının amacı 320x320 model girdisine görüntünün en-boy
    oranını bozarak sıkıştırılmasını engellemektir. Görüntünün kısa kenarı kadar
    bir kare alan merkezden seçilir.

    Args:
        frame: OpenCV/Numpy görüntüsü.
        target_size: (width, height) hedef boyutu.

    Returns:
        320x320 boyutunda işlenmiş OpenCV görüntüsü.
    """
    if frame is None or len(frame.shape) < 2:
        raise ValueError("Geçersiz kamera görüntüsü.")

    height, width = frame.shape[:2]
    side = min(width, height)

    # Kare crop koordinatlarını merkeze göre hesaplıyoruz.
    x0 = (width - side) // 2
    y0 = (height - side) // 2
    square = frame[y0 : y0 + side, x0 : x0 + side]

    # Küçük resimlerin gereksiz yere bulanıklaşmasını engellemek için interpolation
    # yöntemini kaynak/hedef oranına göre seçiyoruz.
    interpolation = cv2.INTER_AREA if side > target_size[0] else cv2.INTER_CUBIC
    return cv2.resize(square, target_size, interpolation=interpolation)


def encode_jpeg_under_limit(frame, max_bytes: int) -> bytes:
    """Görüntüyü JPEG'e dönüştürür ve maksimum byte sınırını sağlamaya çalışır.

    JPEG boyutunu tek bir kalite değeriyle tahmin etmek güvenilir değildir.
    Bu yüzden yüksek kaliteden düşük kaliteye doğru birkaç deneme yapıyoruz.
    Çoğu Raspberry Pi kamera görüntüsü için bu yöntem 50 KB sınırını rahatlıkla
    sağlayacaktır.

    Aşırı detaylı görüntülerde kalite 5'e kadar düşürülebilir. Buna rağmen sınır
    aşılıyorsa son çare olarak görüntüyü gri tonlamaya çeviriyoruz; böylece
    backend'e kesinlikle belirlenen boyut sınırını aşmayan bir payload göndermeye
    çalışıyoruz.

    Args:
        frame: 320x320 OpenCV görüntüsü.
        max_bytes: izin verilen maksimum JPEG boyutu.

    Returns:
        JPEG encoded bytes.

    Raises:
        RuntimeError: Görüntü hiçbir şekilde JPEG olarak encode edilemezse.
    """
    # Öncelikle renkli JPEG için kalite değerlerini kademeli olarak düşürüyoruz.
    for quality in range(90, 4, -5):
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_OPTIMIZE, 1],
        )
        if not ok:
            continue

        data = encoded.tobytes()
        if len(data) <= max_bytes:
            logger.debug("JPEG size=%d bytes, quality=%d", len(data), quality)
            return data

    # Çok gürültülü/karmaşık görüntülerde renk bilgisini kaldırmak dosya boyutunu
    # ciddi şekilde azaltabilir. Model daha sonra gerçek bir model kullanacaksa
    # gri görüntü desteğinin ayrıca doğrulanması gerekir.
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for quality in range(20, 0, -1):
        ok, encoded = cv2.imencode(
            ".jpg",
            gray,
            [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_OPTIMIZE, 1],
        )
        if not ok:
            continue

        data = encoded.tobytes()
        if len(data) <= max_bytes:
            logger.warning(
                "JPEG 50 KB sınırını renkli görüntüyle sağlayamadı; grayscale kullanıldı."
            )
            return data

    raise RuntimeError("Görüntü 50 KB altında JPEG olarak encode edilemedi.")


def send_result(uart: serial.Serial, result: str) -> None:
    """Deneyap Kart'a ONAY veya RED cevabını UART üzerinden gönderir.

    Args:
        uart: Açık pyserial bağlantısı.
        result: Yalnızca ONAY veya RED olması beklenir.
    """
    if result not in {"ONAY", "RED"}:
        raise ValueError(f"Geçersiz UART sonucu: {result}")

    uart.write(result.encode("ascii") + UART_LINE_END)
    uart.flush()
    logger.info("Deneyap Kart <- %s", result)


def analyze_image(session: requests.Session, image_bytes: bytes) -> bool:
    """JPEG görüntüyü FastAPI vision endpoint'ine gönderir.

    requests.Session() kullanılması aynı HTTP bağlantısının tekrar kullanılmasına
    ve Keep-Alive avantajından yararlanılmasına yardımcı olur. Endpoint'in beklediği
    multipart alan adı backend kodundaki UploadFile parametresi nedeniyle 'file'dır.

    Args:
        session: Keep-Alive için kullanılan requests Session nesnesi.
        image_bytes: JPEG görüntü byte dizisi.

    Returns:
        Backend JSON içindeki is_izmarit değerini döndürür.

    Raises:
        requests.RequestException: Ağ, DNS, bağlantı veya timeout hatalarında.
        ValueError: Backend beklenmeyen JSON döndürürse.
        RuntimeError: HTTP status başarısızsa.
    """
    # io.BytesIO fiziksel dosyaya yazmadan görüntüyü bellekte tutmamızı sağlar.
    image_stream = io.BytesIO(image_bytes)

    files = {
        "file": ("capture.jpg", image_stream, "image/jpeg"),
    }

    response = session.post(
        BACKEND_URL,
        files=files,
        timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT),
    )

    # 4xx/5xx response'larda exception üretmek için kullanılır.
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Backend geçerli JSON döndürmedi.") from exc

    # Backend'in önceki adımda tanımlanan sözleşmesini doğruluyoruz.
    if payload.get("status") != "success":
        raise RuntimeError(f"Backend başarısız cevap döndürdü: {payload}")

    is_izmarit = payload.get("is_izmarit")
    if not isinstance(is_izmarit, bool):
        raise ValueError("Backend JSON içinde is_izmarit bool alanı bulunamadı.")

    logger.info(
        "Vision sonucu: is_izmarit=%s, confidence=%s",
        is_izmarit,
        payload.get("confidence"),
    )
    return is_izmarit


def process_photo_request(
    uart: serial.Serial,
    camera: CameraCapture,
    session: requests.Session,
) -> None:
    """Tek bir FOTOGRAF_CEK komutunun uçtan uca işlenmesini gerçekleştirir.

    Kamera çekimi veya ağ iletişimi sırasında herhangi bir hata oluşursa RED
    gönderilir. Böylece Deneyap Kart yeni bir komut göndermeye devam edebilir ve
    edge cihazı tek bir başarısız işlem nedeniyle sonsuz beklemeye girmez.
    """
    try:
        logger.info("Fotoğraf çekiliyor...")
        image_bytes = camera.capture()
        logger.info("Fotoğraf hazır: %d bytes", len(image_bytes))

        # Backend'e gönder ve model sonucunu öğren.
        is_izmarit = analyze_image(session, image_bytes)

        # Model true ise izmarit kabul edilir, false ise reddedilir.
        send_result(uart, "ONAY" if is_izmarit else "RED")

    except requests.Timeout as exc:
        # Kullanıcının özellikle istediği timeout davranışı: sistem donmaz,
        # kart tarafına güvenli varsayılan sonuç olan RED gönderilir.
        logger.error("Backend timeout: %s", exc)
        try:
            send_result(uart, "RED")
        except SerialException:
            logger.exception("Timeout sonrasında RED UART'a gönderilemedi.")

    except requests.RequestException as exc:
        # DNS, bağlantı reddi, connection reset vb. ağ sorunları.
        logger.error("Backend ağ hatası: %s", exc)
        try:
            send_result(uart, "RED")
        except SerialException:
            logger.exception("Ağ hatası sonrasında RED UART'a gönderilemedi.")

    except Exception as exc:
        # Kamera/JSON/encode gibi beklenmeyen tüm hatalarda da edge cihazı
        # çalışmaya devam eder; güvenli varsayılan olarak RED gönderilir.
        logger.exception("Fotoğraf işlemi sırasında hata: %s", exc)
        try:
            send_result(uart, "RED")
        except SerialException:
            logger.exception("Hata sonrasında RED UART'a gönderilemedi.")


def main() -> None:
    """Edge agent'in ana olay döngüsünü başlatır.

    UART bağlantısı oluşturulur, kamera hazırlanır ve requests.Session() açılır.
    Bundan sonra Deneyap Kart'tan satır bazlı komutlar okunur. Sadece
    'FOTOGRAF_CEK' komutu işlenir; diğer komutlar görmezden gelinir.
    """
    logger.info("EkoMatik Edge Agent başlatılıyor...")
    logger.info("UART=%s | baud=%d", UART_PORT, UART_BAUDRATE)
    logger.info("Vision endpoint=%s", BACKEND_URL)

    camera: Optional[CameraCapture] = None
    session = requests.Session()

    # Session header'ı opsiyonel olarak cihazı tanımlamak için kullanılabilir.
    # Vision endpoint'i şu an bu header'a ihtiyaç duymuyor; ileride rate-limit,
    # device-id veya observability için backend'de kullanılabilir.
    session.headers.update({"User-Agent": "EkoMatik-RPiZero-Edge/1.0"})

    try:
        # SerialException oluşursa ana program kontrollü şekilde kapanacaktır.
        with serial.Serial(
            port=UART_PORT,
            baudrate=UART_BAUDRATE,
            timeout=1.0,
            write_timeout=2.0,
        ) as uart:
            camera = CameraCapture(CAMERA_INDEX)
            logger.info("Edge Agent hazır. Deneyap Kart komutu bekleniyor...")

            while True:
                try:
                    # readline timeout=1.0 sayesinde program sonsuza kadar bloke olmaz.
                    raw_command = uart.readline()
                    if not raw_command:
                        continue

                    command = raw_command.decode("utf-8", errors="ignore").strip()
                    if not command:
                        continue

                    logger.info("Deneyap Kart -> %s", command)

                    if command == "FOTOGRAF_CEK":
                        process_photo_request(uart, camera, session)
                    else:
                        # Bilinmeyen komutlar protokolü bozmayacak şekilde yok sayılır.
                        logger.warning("Bilinmeyen UART komutu: %r", command)

                except SerialException as exc:
                    # UART anlık olarak düşerse döngünün içine yeniden bağlanma
                    # mekanizması eklemek yerine burada kontrollü hata veriyoruz.
                    # Systemd ile servis olarak çalıştırıldığında yeniden başlatılabilir.
                    logger.error("UART bağlantısı koptu: %s", exc)
                    break

    except SerialException as exc:
        logger.error("UART açılamadı (%s): %s", UART_PORT, exc)
        raise
    finally:
        camera.close() if camera is not None else None
        session.close()
        logger.info("EkoMatik Edge Agent kapatıldı.")


if __name__ == "__main__":
    main()