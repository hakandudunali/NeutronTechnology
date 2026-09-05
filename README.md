# 🚬 EkoMatik

**EkoMatik**, atık sigara izmaritlerinin kontrollü şekilde toplanmasını, görüntü üzerinden kontrol edilmesini, tartılmasını ve kullanıcıların topladıkları atık karşılığında puan kazanmasını amaçlayan IoT tabanlı akıllı geri dönüşüm sistemidir.

Bu repository, projenin ilk jüri raporundan sonraki **güncel prototip yapısını**, yapılan mimari değişiklikleri ve sonraki geliştirme hedeflerini içerir. İlk rapor, geliştirme sürecinin erken aşamasındaki tasarımı temsil etmektedir; prototip geliştikçe bazı donanım ve yazılım kararları güncellenmiştir.

##  Güncel Sistem Mimarisi

```text
Kamera / Görüntü Yakalama
          │
          ▼
      İnternet
          │
          ▼
┌────────────────────────┐
│       Backend          │
│        FastAPI         │
│                        │
│  Görüntü İşleme        │
│  İşlem Yönetimi        │
│  Kullanıcı / Bakiye    │
└───────────┬────────────┘
            │
            ▼
       PostgreSQL
            │
            ▼
      Flutter Mobil App

Deneyap Kart ◄── Internet ──► Backend
     │
     ├── RFID
     ├── Loadcell + HX711
     ├── Servo
     └── LCD
```

##  Güncel Çalışma Mantığı

1. Kullanıcı RFID ile tanımlanır.
2. Kamera ile atığın görüntüsü alınır.
3. Görüntü internet üzerinden görüntü işleme servisinin bulunduğu sisteme gönderilir.
4. Sunucu görüntüyü analiz eder ve **ONAY / RED** sonucu üretir.
5. Sonuç Deneyap Kart'a iletilir.
6. Kabul edilen atık için mekanizma ve tartım süreci çalıştırılır.
7. Loadcell + HX711 ile ağırlık ölçülür.
8. Mevcut prototipte puan hesabı `gram × 1,4` katsayısı ile yapılır.
9. İşlem güvenli şekilde backend'e aktarılır ve kullanıcı bakiyesine işlenir.
10. Kullanıcı bakiyesini mobil uygulama üzerinden görüntüleyebilir.

##  Görüntü İşleme – Güncel Yaklaşım

İlk tasarımda görüntü işleme işleminin Raspberry Pi üzerinde gerçekleştirilmesi planlanmıştı. Geliştirme sürecinde bu yaklaşım değiştirilmiştir.

Güncel hedef mimaride kamera/görüntü yakalama birimi fotoğrafı alır ve internet üzerinden sisteme gönderir. **Görüntü işleme ve izmarit sınıflandırması sunucu tarafında gerçekleştirilir.** Analiz sonucu tekrar sisteme iletilir ve Deneyap Kart bu sonuca göre işlemi devam ettirir veya sonlandırır.

Repository'deki mevcut edge yazılımı kamera görüntüsünü yakalama, temel görüntü ön işleme ve backend'e gönderme görevlerini yürütmektedir. Görüntü sınıflandırma tarafındaki mevcut backend implementasyonu ise prototip/test amaçlıdır; gerçek model entegrasyonu sonraki geliştirme aşamasıdır.

##  Donanım

- Deneyap Kart
- HX711
- Loadcell
- SG90 Servo Motor
- RC522 RFID okuyucu
- LCD ekran
- Kamera
- Yardımcı buton/sensörler

##  Yazılım

### Deneyap

`ekomatik_deneyap/` klasöründe Deneyap Kart firmware'i bulunur. RFID, loadcell, servo, LCD, Wi-Fi ve backend haberleşmesini yönetir.

### Edge / Kamera

`ekomatik_edge/` klasöründe kamera görüntüsünü alan ve internet üzerinden backend görüntü işleme endpoint'ine gönderen edge yazılımı bulunur.

### Backend

`ekomatik_backend/` klasöründe FastAPI + PostgreSQL tabanlı servis bulunur. Kullanıcı, RFID kart, bakiye ve işlem yönetiminin yanı sıra görüntü işleme endpoint'i de burada yer alır.

### Mobil Uygulama

`ekomatik_flutter/` klasöründe Flutter tabanlı mobil uygulama bulunur. Temel olarak bakiye görüntüleme, RFID kart bağlantısı ve puan kullanım işlemlerini içerir.

##  Güvenlik

Deneyap Kart ile backend arasındaki işlem aktarımında HMAC-SHA256 tabanlı doğrulama kullanılmaktadır. Repository'de gerçek Wi-Fi bilgileri veya üretim secret'ları bulunmamalıdır.

Firmware içerisindeki `YOUR_HMAC_SECRET`, gerçek cihaz yapılandırmasında değiştirilmesi gereken bir placeholder'dır. Benzer şekilde Wi-Fi ve backend adresleri de gerçek ortamda yapılandırılmalıdır.

##  Gelecek Geliştirmeler

- Gerçek görüntü işleme modelinin entegrasyonu ve doğruluğunun artırılması
- Kamera → internet → görüntü işleme → Deneyap Kart akışının kararlılığının artırılması
- Loadcell kalibrasyonu ve ölçüm hassasiyetinin geliştirilmesi
- Mekanik yapının son ürün için iyileştirilmesi
- Mobil uygulamanın kullanıcı deneyiminin geliştirilmesi
- Bağış ve ulaşım servisleri gibi harici entegrasyonların eklenmesi
- İşlem tekrarları, bağlantı kesintileri ve hata durumları için daha güçlü kontrol mekanizmaları

##  Proje Durumu

| Bileşen | Durum |
|---|---|
| Deneyap Kart kontrolü | 🟢 Prototip / geliştiriliyor |
| Loadcell + HX711 | 🟢 Prototip / geliştiriliyor |
| Servo mekanizması | 🟢 Prototip / geliştiriliyor |
| RFID | 🟢 Prototip |
| Backend | 🟢 Geliştiriliyor |
| PostgreSQL | 🟢 Kullanılıyor |
| Flutter mobil uygulama | 🟡 Geliştiriliyor |
| İnternet tabanlı görüntü işleme altyapısı | 🟡 Geliştiriliyor |
| Harici servis entegrasyonları | 🔵 Gelecek geliştirme |

##  Klasör Yapısı

```text
EkoMatik/
├── ekomatik_deneyap/
│   ├── ekomatik_deneyap.ino
│   └── README.md
├── ekomatik_edge/
│   ├── edge_agent.py
│   ├── requirements.txt
│   └── README.md
├── ekomatik_backend/
│   ├── app/
│   ├── requirements.txt
│   ├── docker-compose.yml
│   ├── .env.example
│   └── README.md
├── ekomatik_flutter/
│   ├── lib/
│   ├── pubspec.yaml
│   └── README.md
├── .gitignore
└── README.md
```

> **Not:** Proje aktif geliştirme aşamasındadır. Donanım, görüntü işleme ve harici servis entegrasyonları prototip testlerinin sonuçlarına göre güncellenmeye devam etmektedir.
