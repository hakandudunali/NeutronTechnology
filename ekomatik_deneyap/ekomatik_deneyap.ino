/*
 * ================================================================
 * EkoMatik - Deneyap Kart 1A / ESP32 Core Firmware
 * ================================================================
 *
 * Bu firmware EkoMatik sisteminin ana kontrol birimidir.
 * Deneyap Kart; RFID kartini okur, kullanicinin izmariti birakmasini
 * bekler, Raspberry Pi Zero'dan goruntu analizi sonucu alir, izmaritin
 * onaylanmasi durumunda servo mekanizmasini acip loadcell ile agirligi
 * olcer, puani hesaplar ve sonucu HMAC-SHA256 ile imzalayarak FastAPI
 * backend'ine HTTPS uzerinden gonderir.
 *
 * Durum makinesi:
 *   IDLE -> WAIT_ITEM -> WAIT_ML -> WEIGHING -> SYNC -> API -> FINISH -> IDLE
 *
 * Gerekli Arduino kutuphaneleri:
 *   - WiFi
 *   - WiFiClientSecure
 *   - HTTPClient
 *   - SPI
 *   - MFRC522
 *   - Wire
 *   - LiquidCrystal_I2C
 *   - HX711
 *   - ESP32Servo
 *   - ArduinoJson
 *   - mbedTLS (ESP32 Arduino Core ile birlikte gelir)
 *
 * NOT:
 * Kullanici tarafindan verilen pinler firmware'de aynen kullanilmistir.
 * Deneyap Kart 1A'nin resmi dokumantasyonunda varsayilan SPI/I2C/UART
 * pinleri farkli olabildigi icin gercek kart revizyonu ile elektriksel
 * baglantilar mutlaka kontrol edilmelidir.
 *
 * Guvenlik NOTU:
 * HTTPS icin prototipte setInsecure() kullanilmistir. Uretim sisteminde
 * sunucunun CA kok sertifikasi PROGMEM icinde tanimlanip setCACert() ile
 * kullanilmalidir.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <Wire.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>
#include <HX711.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include "mbedtls/md.h"

// ================================================================
// 1. DONANIM PINLERI
// ================================================================

// RC522 RFID
const int RFID_SS_PIN  = 5;    // RC522 SDA/SS chip-select pini.
const int RFID_RST_PIN = 22;   // RC522 reset pini.

// Kullanici isteginde SPI'nin SCK/MISO/MOSI pinleri belirtilmedigi icin
// bunlar ayarlanabilir sabitler olarak birakilmistir.
// Deneyap Kart 1A'nin resmi SPI pinlerine gore veya fiziksel kablolamaya gore degistirilebilir.
const int RFID_SCK_PIN  = 19;
const int RFID_MISO_PIN = 27;
const int RFID_MOSI_PIN = 26;

// I2C LCD
// Kullanici sadece I2C hattini ve LCD adresini belirttigi icin SDA/SCL
// kartin Wire varsayilanlarinda birakilabilir. Gerekirse burada pin atanabilir.
const int I2C_SDA_PIN = 4;
const int I2C_SCL_PIN = 15;
const uint8_t LCD_ADDRESS = 0x27;

// HX711 Load Cell Amplifier
const int HX711_DOUT_PIN = 32;
const int HX711_SCK_PIN  = 33;

// Servo
const int SERVO_PIN = 18;

// Raspberry Pi Zero UART2
const int PI_UART_RX_PIN = 16;
const int PI_UART_TX_PIN = 17;
const long PI_UART_BAUDRATE = 115200;

// Izmarit girisini simule eden buton.
// Buton bir GPIO'ya baglanirsa LOW oldugunda atik birakildi kabul edilir.
// Gercek urunde bir IR sensoru, limit switch veya agirlik esik kontrolu
// ile degistirilebilir.
const int ITEM_BUTTON_PIN = 25;

// ================================================================
// 2. WIFI / BACKEND AYARLARI
// ================================================================

// Wi-Fi SSID ve sifresi cihaz flash'inda tutulacagi icin uretimde
// kaynak koduna sabit olarak yazmak yerine cihaz bazli guvenli bir
// provisioning mekanizmasi tercih edilmelidir.
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// FastAPI backend adresi.
// Ornek: https://api.ekomatik.local veya https://192.168.1.100:8000
const char* API_URL = "https://YOUR_BACKEND_HOST:8000/api/v1/transactions/add";

// Backend ile ortak kullanilan statik secret.
// URETIMDE kesinlikle ornek deger kullanilmamali ve cihaz bazli secret
// yonetimi uygulanmalidir.
const char* SECRET_KEY = "YOUR_HMAC_SECRET";

// HTTP ve UART bekleme timeout degerleri.
const uint32_t HTTP_CONNECT_TIMEOUT_MS = 5000;
const uint32_t HTTP_RESPONSE_TIMEOUT_MS = 8000;
const uint32_t ML_TIMEOUT_MS = 15000;
const uint32_t ITEM_WAIT_TIMEOUT_MS = 5000;

// ================================================================
// 3. LOAD CELL KALIBRASYON
// ================================================================

// Bu deger MOCK kalibrasyon faktorudur.
// Gercek loadcell + HX711 kurulumu kullanildiginda bilinen bir agirlik
// ile calibration_factor yeniden belirlenmelidir.
float calibration_factor = 420.0f;

// Izmarit basina puan katsayisi: puan = gramaj * 1.4
const float POINT_RATE_PER_GRAM = 1.4f;

// Servo aci degerleri.
const int SERVO_CLOSED_ANGLE = 0;
const int SERVO_OPEN_ANGLE   = 90;

// ================================================================
// 4. DURUM MAKINESI
// ================================================================

enum SystemState {
  STATE_IDLE,
  STATE_WAIT_ITEM,
  STATE_WAIT_ML,
  STATE_WEIGHING,
  STATE_SYNC,
  STATE_API,
  STATE_FINISH
};

SystemState currentState = STATE_IDLE;

// Durum degisikliklerinde millis() tabanli timeout ve bekleme islemleri
// icin kullanilan zaman damgasi.
uint32_t stateStartedAt = 0;

// ================================================================
// 5. GLOBAL NESNELER
// ================================================================

// RFID okuyucu nesnesi.
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);

// I2C LCD nesnesi: 16x2.
LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);

// HX711 loadcell nesnesi.
HX711 scale;

// Servo nesnesi.
Servo gateServo;

// Raspberry Pi Zero ile haberlesen ikinci UART.
HardwareSerial PiSerial(2);

// HTTP Keep-Alive icin global Session mantigi HTTPClient + WiFiClientSecure
// kombinasyonu ile saglanir. WiFiClientSecure nesnesini yeniden yaratmak
// yerine global kullanarak TLS istemci nesnesini tekrar kullanabiliriz.
WiFiClientSecure secureClient;
HTTPClient http;

// ================================================================
// 6. OTURUM / ISLEM VERILERI
// ================================================================

String currentRfidUid = "";
float currentWeightGrams = 0.0f;
float currentPoints = 0.0f;
uint32_t currentUnixTimestamp = 0;
String currentHmac = "";

// API sonucundan sonra LCD'deki basari mesajinin 3 saniye tutulmasi icin.
uint32_t finishStartedAt = 0;

// ================================================================
// 7. YARDIMCI FONKSIYONLAR
// ================================================================

/*
 * LCD'nin iki satirini temizleyerek verilen metni ekrana yazar.
 *
 * Neden ayri fonksiyon?
 * LCD kodunu state machine icindeki her case'te tekrar tekrar yazmak
 * yerine tum ekran islemlerini tek noktada toplamak bakimi kolaylastirir.
 */
void showLCD(const String& line1, const String& line2 = "") {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));
  lcd.setCursor(0, 1);
  lcd.print(line2.substring(0, 16));
}

/*
 * State machine durumunu degistirir ve durum baslangic zamanini sifirlar.
 * Bu zaman bilgisi, 5 saniyelik atik bekleme ve ML timeout gibi islemlerde
 * non-blocking zaman kontrolu yapmak icin kullanilir.
 */
void changeState(SystemState newState) {
  currentState = newState;
  stateStartedAt = millis();
}

/*
 * Aktif state'in ne kadar suredir devam ettigini milisaniye cinsinden doner.
 * millis() overflow durumunu dogal olarak destekleyen unsigned cikarma
 * mantigi kullanilir.
 */
uint32_t stateElapsedMs() {
  return millis() - stateStartedAt;
}

/*
 * Deneyap Kart'in UART2 hatti uzerinden Raspberry Pi Zero'ya satir komutu gonderir.
 * Her komutun sonunda newline bulunur; Pi tarafindaki readline() bununla
 * mesaj sonunu anlayabilir.
 */
void sendPiCommand(const char* command) {
  PiSerial.print(command);
  PiSerial.print('\n');
}

/*
 * UART tamponunda biriken satiri okur.
 *
 * Fonksiyonun temel amaci WAIT_ML state'inde ONAY veya RED cevaplarini
 * blocking bir while icinde sonsuza kadar beklemeden almaktir.
 */
String readPiLine() {
  static String buffer;

  while (PiSerial.available()) {
    char c = static_cast<char>(PiSerial.read());

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      String line = buffer;
      buffer = "";
      line.trim();
      return line;
    }

    // UART'tan cok uzun/bozuk bir frame gelmesi halinde RAM'in gereksiz
    // buyumesini engellemek icin buffer sinirlanir.
    if (buffer.length() < 64) {
      buffer += c;
    }
  }

  return "";
}

/*
 * RFID kart UID'sini hexadecimal ve buyuk harf formatinda String'e cevirir.
 * Ornek: A1 B2 C3 D4 -> "A1B2C3D4"
 */
String readRfidUid() {
  String uid = "";

  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) {
      uid += "0";
    }

    uid += String(rfid.uid.uidByte[i], HEX);
  }

  uid.toUpperCase();
  return uid;
}

/*
 * HMAC-SHA256 hash sonucunu 64 karakterlik hexadecimal String'e cevirir.
 * mbedTLS, ESP32 Arduino Core tarafinda kullanilabilen guvenilir kriptografi
 * katmanidir; bu nedenle hash islemini elle yazmak yerine dogrudan mbedTLS
 * API'si kullanilir.
 */
String bytesToHex(const unsigned char* data, size_t length) {
  const char* hex = "0123456789abcdef";
  String output;
  output.reserve(length * 2);

  for (size_t i = 0; i < length; ++i) {
    output += hex[(data[i] >> 4) & 0x0F];
    output += hex[data[i] & 0x0F];
  }

  return output;
}

/*
 * HMAC-SHA256 hesaplar.
 *
 * KULLANILAN IMZA SOZLESMESI:
 *     message = <rfid_uid><puan><timestamp>
 *
 * Ornegin:
 *     A1B2C3D41.54<unix_timestamp>
 *
 * Backend de ayni canonical string'i ayni SECRET_KEY ile HMAC'lemelidir.
 * Bu ayrinti kritik oneme sahiptir; JSON body'sini imzalamak ile yukaridaki
 * birlestirilmis string'i imzalamak ayni hash sonucunu uretmez.
 */
String calculateHMAC(const String& rfidUid, float points, uint32_t timestamp) {
  // Puanin JSON'a girecek formatla ayni olmasi icin iki ondalik basamak kullanilir.
  String pointsString = String(points, 2);

  // Kullanici tarafindan belirtilen canonical signing string.
  String message = rfidUid + pointsString + String(timestamp);

  unsigned char hmacResult[32];

  const mbedtls_md_info_t* mdInfo = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (mdInfo == nullptr) {
    Serial.println("[HMAC] SHA-256 algoritmasi bulunamadi!");
    return "";
  }

  int result = mbedtls_md_hmac(
    mdInfo,
    reinterpret_cast<const unsigned char*>(SECRET_KEY),
    strlen(SECRET_KEY),
    reinterpret_cast<const unsigned char*>(message.c_str()),
    message.length(),
    hmacResult
  );

  if (result != 0) {
    Serial.printf("[HMAC] mbedTLS hata kodu: %d\n", result);
    return "";
  }

  return bytesToHex(hmacResult, sizeof(hmacResult));
}

/*
 * Wi-Fi bağlantısını kurar.
 *
 * Cihaz zaten bagliysa tekrar connection acmak yerine mevcut baglantiyi korur.
 * Bekleme suresi sonsuz degildir; boylece devlet makinesi Wi-Fi yokken tamamen
 * kilitlenmez.
 */
bool connectWiFi(uint32_t timeoutMs = 15000) {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.println("[WIFI] Baglaniyor...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t start = millis();

  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    delay(250);
    Serial.print('.');
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WIFI] IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("[WIFI] Baglanti basarisiz.");
  return false;
}

/*
 * NTP sunucusundan gecerli UNIX timestamp alir.
 *
 * Backend'in replay protection mekanizmasi icin cihaz zamaninin dogru olmasi
 * zorunludur. Bu nedenle API isteginden once NTP senkronizasyonu yapilir.
 */
bool syncTimeAndGetTimestamp(uint32_t& timestampOut) {
  if (!connectWiFi()) {
    return false;
  }

  // UTC kullanilir. UNIX timestamp zaten timezone bagimsizdir.
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  struct tm timeInfo;
  uint32_t start = millis();

  while (!getLocalTime(&timeInfo, 1000)) {
    if (millis() - start > 10000) {
      Serial.println("[NTP] Zaman senkronizasyonu timeout.");
      return false;
    }
  }

  time_t now = time(nullptr);

  // 2024 sonrasindaki makul bir UNIX timestamp kontrolu ile NTP'nin gercekten
  // senkronize olup olmadigini basitce dogrulariz.
  if (now < 1700000000) {
    Serial.println("[NTP] Gecersiz sistem zamani.");
    return false;
  }

  timestampOut = static_cast<uint32_t>(now);
  Serial.printf("[NTP] UNIX timestamp: %lu\n", static_cast<unsigned long>(timestampOut));
  return true;
}

/*
 * HX711 loadcell'i baslatir ve mock calibration factor'u uygular.
 */
bool initializeLoadCell() {
  scale.begin(HX711_DOUT_PIN, HX711_SCK_PIN);

  if (!scale.wait_ready_timeout(2000)) {
    Serial.println("[HX711] Sensor hazir degil.");
    return false;
  }

  scale.set_scale(calibration_factor);
  scale.tare();

  Serial.println("[HX711] Baslatildi ve tare yapildi.");
  return true;
}

/*
 * Servo kapisi icin varsayilan konumu ayarlar.
 * SG90'un ESP32 PWM ile calismasi icin ESP32Servo kutuphanesi kullanilir.
 */
void initializeServo() {
  // ESP32Servo, timer/pwm kaynaklarini servo kontrolu icin yonetir.
  gateServo.setPeriodHertz(50);
  gateServo.attach(SERVO_PIN, 500, 2400);
  gateServo.write(SERVO_CLOSED_ANGLE);
}

/*
 * Bir adet tartim alir ve gram cinsine cevirir.
 * HX711 kutuphanesi burada calibration factor'u kullanarak dogrudan
 * kalibre edilmis birim verir.
 */
float readWeightGrams() {
  if (!scale.wait_ready_timeout(2000)) {
    Serial.println("[HX711] Tartim sirasinda sensor hazir degil.");
    return -1.0f;
  }

  // Noise azaltmak icin 5 ortalama okuma kullanilir.
  float weight = scale.get_units(5);

  // Fiziksel sistemde sifirin altina dusen kucuk sensor sapmalari 0'a cekilir.
  if (weight < 0.0f) {
    weight = 0.0f;
  }

  return weight;
}

/*
 * Puan hesabini gerceklestirir.
 * Formul kullanicinin belirttigi sekildedir:
 *     puan = gramaj * 1.4
 */
float calculatePoints(float grams) {
  return grams * POINT_RATE_PER_GRAM;
}

/*
 * FastAPI /transactions/add endpointine guvenli POST gonderir.
 *
 * JSON:
 *   {
 *     "rfid_uid": "A1B2C3D4",
 *     "amount": 1.54,
 *     "timestamp": 1725464503
 *   }
 *
 * Header:
 *   Authorization: Bearer <HMAC_HEX>
 *
 * TLS icin WiFiClientSecure kullanilir.
 */
bool sendToAPI(const String& rfidUid, float points, uint32_t timestamp, const String& signature) {
  if (!connectWiFi()) {
    Serial.println("[API] Wi-Fi yok.");
    return false;
  }

  if (signature.length() != 64) {
    Serial.println("[API] Gecersiz HMAC uzunlugu.");
    return false;
  }

  // --------------------------------------------------------------
  // JSON payload olusturma
  // --------------------------------------------------------------
  // ArduinoJson kullanmak, String ile elle JSON birlestirmeye gore daha
  // guvenlidir; ayrica ileride alan sayisi arttirilabilir.
  JsonDocument requestJson;
  requestJson["rfid_uid"] = rfidUid;
  requestJson["amount"] = points;
  requestJson["timestamp"] = timestamp;

  String requestBody;
  serializeJson(requestJson, requestBody);

  Serial.print("[API] Payload: ");
  Serial.println(requestBody);

  // --------------------------------------------------------------
  // HTTPS/TLS istemcisi
  // --------------------------------------------------------------
  // PROTOTIP:
  // Sertifika dogrulamasi devre disi birakilmistir.
  // Uretimde server CA sertifikasi setCACert() ile yuklenmelidir.
  secureClient.setInsecure();
  secureClient.setTimeout(HTTP_RESPONSE_TIMEOUT_MS / 1000);

  // HTTPClient nesnesini ayni global WiFiClientSecure uzerinden kullaniyoruz.
  // Keep-Alive icin Connection: keep-alive header'i eklenir.
  if (!http.begin(secureClient, API_URL)) {
    Serial.println("[API] HTTP begin() basarisiz.");
    return false;
  }

  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_RESPONSE_TIMEOUT_MS);
  http.useHTTP10(false); // HTTP/1.1 -> persistent connection/Keep-Alive.

  http.addHeader("Content-Type", "application/json");
  http.addHeader("Accept", "application/json");
  http.addHeader("Connection", "keep-alive");
  http.addHeader("Authorization", String("Bearer ") + signature);

  // --------------------------------------------------------------
  // POST islemi
  // --------------------------------------------------------------
  int statusCode = http.POST(requestBody);

  if (statusCode <= 0) {
    // HTTPClient negatif kodlari baglanti/timeout gibi transport problemlerini
    // temsil eder. Bu durumda cihazda basarisiz kabul edilip RED akisi uygulanir.
    Serial.printf("[API] Transport hatasi: %d - %s\n", statusCode, http.errorToString(statusCode).c_str());
    http.end();
    return false;
  }

  String responseBody = http.getString();
  Serial.printf("[API] HTTP status: %d\n", statusCode);
  Serial.print("[API] Response: ");
  Serial.println(responseBody);

  bool success = (statusCode == 200);

  // Backend basarili yanitta JSON donuyorsa opsiyonel olarak status alanini
  // de kontrol ediyoruz. HTTP 200 geldiyse ana kabul kosulu budur.
  if (success && responseBody.length() > 0) {
    JsonDocument responseJson;
    DeserializationError error = deserializeJson(responseJson, responseBody);

    if (!error) {
      const char* status = responseJson["status"] | "";
      if (strlen(status) > 0 && String(status) != "success") {
        success = false;
      }
    }
  }

  http.end();
  return success;
}

/*
 * RFID kart okuma dongusunu guvenli hale getirir.
 * Yeni kart algilanmadiysa false doner; kart varsa UID okunur ve true doner.
 */
bool readNewRfidCard(String& uidOut) {
  // PICC_IsNewCardPresent() yeni bir kartin alan icine girdigini kontrol eder.
  if (!rfid.PICC_IsNewCardPresent()) {
    return false;
  }

  // PICC_ReadCardSerial() UID'yi okuyamazsa false doner.
  if (!rfid.PICC_ReadCardSerial()) {
    return false;
  }

  uidOut = readRfidUid();

  // Okuma tamamlaninca kart ile haberlesmeyi sonlandiriyoruz.
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  return uidOut.length() > 0;
}

/*
 * Uyari/hata mesajini LCD'de gosterir, ardindan cihaz STATE_IDLE'a doner.
 * Bu fonksiyon sistemin herhangi bir beklenmeyen durumda kilitlenmesini onler.
 */
void failAndReturnToIdle(const String& firstLine, const String& secondLine = "Tekrar deneyin") {
  showLCD(firstLine, secondLine);
  sendPiCommand("RED");
  delay(1000);
  gateServo.write(SERVO_CLOSED_ANGLE);
  changeState(STATE_IDLE);
  showLCD("Kartinizi", "Okutun");
}

// ================================================================
// 8. SETUP
// ================================================================

void setup() {
  // USB Serial, yalnizca debug/gelistirme icin kullanilir.
  Serial.begin(115200);
  delay(200);

  Serial.println();
  Serial.println("====================================");
  Serial.println("EkoMatik Deneyap Firmware basliyor");
  Serial.println("====================================");

  // --------------------------------------------------------------
  // LCD / I2C
  // --------------------------------------------------------------
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  lcd.init();
  lcd.backlight();
  showLCD("EkoMatik", "Baslatiliyor...");

  // --------------------------------------------------------------
  // Raspberry Pi UART2
  // --------------------------------------------------------------
  // HardwareSerial(2) kullanilarak UART2 RX=16 TX=17 atanir.
  PiSerial.begin(
    PI_UART_BAUDRATE,
    SERIAL_8N1,
    PI_UART_RX_PIN,
    PI_UART_TX_PIN
  );

  // --------------------------------------------------------------
  // Buton / atik algilama simulasyonu
  // --------------------------------------------------------------
  pinMode(ITEM_BUTTON_PIN, INPUT_PULLUP);

  // --------------------------------------------------------------
  // Servo
  // --------------------------------------------------------------
  initializeServo();

  // --------------------------------------------------------------
  // SPI + RC522
  // --------------------------------------------------------------
  // Servo pini ile standart ESP32 VSPI arasinda olasi pin cakismalarini
  // onlemek icin SPI pinleri acikca verilmistir.
  SPI.begin(RFID_SCK_PIN, RFID_MISO_PIN, RFID_MOSI_PIN, RFID_SS_PIN);
  rfid.PCD_Init();
  delay(50);

  // --------------------------------------------------------------
  // HX711
  // --------------------------------------------------------------
  if (!initializeLoadCell()) {
    showLCD("HX711 Hatasi", "Sensor kontrol");
    // Sensor daha sonra tekrar denenebilsin diye burada return etmiyoruz.
  }

  // --------------------------------------------------------------
  // Wi-Fi
  // --------------------------------------------------------------
  connectWiFi();

  // İlk acilista cihaz her zaman IDLE'a doner.
  changeState(STATE_IDLE);
  showLCD("Kartinizi", "Okutun");
}

// ================================================================
// 9. LOOP / STATE MACHINE
// ================================================================

void loop() {
  switch (currentState) {

    // ============================================================
    // STATE_IDLE
    // ============================================================
    case STATE_IDLE: {
      // Kullaniciya sistemin yeni RFID kartini bekledigini bildiriyoruz.
      // Ekran her dongude clear edilmez; boylece LCD titremesi azalir.
      static bool idleScreenShown = false;
      if (!idleScreenShown) {
        showLCD("Kartinizi", "Okutun");
        idleScreenShown = true;
      }

      // Yeni RFID karti tespit edilirse UID'yi aliriz.
      String uid;
      if (readNewRfidCard(uid)) {
        idleScreenShown = false;
        currentRfidUid = uid;

        Serial.print("[RFID] UID: ");
        Serial.println(currentRfidUid);

        showLCD("Izmariti", "Birakin");
        changeState(STATE_WAIT_ITEM);
      }

      break;
    }

    // ============================================================
    // STATE_WAIT_ITEM
    // ============================================================
    case STATE_WAIT_ITEM: {
      // Gercek urunde burada sensor, switch, IR bariyer vb. kullanilabilir.
      // Prototype icin buton veya 5 saniyelik otomatik bekleme kullanilir.
      bool itemDetected = (digitalRead(ITEM_BUTTON_PIN) == LOW);
      bool autoTimeout = stateElapsedMs() >= ITEM_WAIT_TIMEOUT_MS;

      if (itemDetected || autoTimeout) {
        Serial.println("[ITEM] Atik girisi algilandi.");

        // Pi Zero'ya goruntu cekmesini soyluyoruz.
        sendPiCommand("FOTOGRAF_CEK");

        showLCD("Analiz", "Ediliyor...");
        changeState(STATE_WAIT_ML);
      }

      break;
    }

    // ============================================================
    // STATE_WAIT_ML
    // ============================================================
    case STATE_WAIT_ML: {
      // Pi Zero tarafindan gelen satiri blocking olmadan okuruz.
      String response = readPiLine();

      if (response.length() > 0) {
        Serial.print("[PI] Cevap: ");
        Serial.println(response);

        response.toUpperCase();

        if (response == "ONAY") {
          // Izmarit onaylandi. Mekanizma acilir.
          gateServo.write(SERVO_OPEN_ANGLE);
          showLCD("Izmarit", "Onaylandi");
          changeState(STATE_WEIGHING);
        } else if (response == "RED") {
          // Izmarit tespit edilmediyse veya Edge hata verdiyse kullaniciya
          // hata gosterip yeni islemi bekleriz.
          showLCD("Izmarit", "Reddedildi");
          delay(1000);
          gateServo.write(SERVO_CLOSED_ANGLE);
          changeState(STATE_IDLE);
          showLCD("Kartinizi", "Okutun");
        }
      }

      // Pi Zero beklenmedik sekilde cevap vermezse cihaz sonsuza kadar
      // WAIT_ML state'inde kalmamalidir.
      if (stateElapsedMs() > ML_TIMEOUT_MS) {
        Serial.println("[ML] Pi Zero cevap timeout.");
        showLCD("Analiz Hatasi", "Tekrar deneyin");
        delay(1000);
        gateServo.write(SERVO_CLOSED_ANGLE);
        changeState(STATE_IDLE);
        showLCD("Kartinizi", "Okutun");
      }

      break;
    }

    // ============================================================
    // STATE_WEIGHING
    // ============================================================
    case STATE_WEIGHING: {
      showLCD("Tartiliyor...", "Lutfen bekleyin");

      currentWeightGrams = readWeightGrams();

      if (currentWeightGrams < 0.0f) {
        Serial.println("[WEIGHT] Loadcell hatasi.");
        showLCD("Tartim Hatasi", "Tekrar deneyin");
        delay(1000);
        gateServo.write(SERVO_CLOSED_ANGLE);
        changeState(STATE_IDLE);
        showLCD("Kartinizi", "Okutun");
        break;
      }

      // Kullanici tarafindan verilen puan formulu uygulanir.
      currentPoints = calculatePoints(currentWeightGrams);

      Serial.printf("[WEIGHT] %.2f g -> %.2f puan\n", currentWeightGrams, currentPoints);

      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Agirlik:");
      lcd.print(String(currentWeightGrams, 1));
      lcd.print("g");
      lcd.setCursor(0, 1);
      lcd.print("Puan:");
      lcd.print(String(currentPoints, 2));

      changeState(STATE_SYNC);
      break;
    }

    // ============================================================
    // STATE_SYNC
    // ============================================================
    case STATE_SYNC: {
      showLCD("Sunucu", "senkronize...");

      // NTP ile guncel UNIX timestamp alinir.
      if (!syncTimeAndGetTimestamp(currentUnixTimestamp)) {
        Serial.println("[SYNC] NTP basarisiz.");
        showLCD("Ag Hatasi", "Tekrar deneyin");
        delay(1000);
        gateServo.write(SERVO_CLOSED_ANGLE);
        changeState(STATE_IDLE);
        showLCD("Kartinizi", "Okutun");
        break;
      }

      // Kullanici tarafindan istenen canonical string uzerinden HMAC-SHA256.
      currentHmac = calculateHMAC(
        currentRfidUid,
        currentPoints,
        currentUnixTimestamp
      );

      if (currentHmac.length() != 64) {
        Serial.println("[SYNC] HMAC uretilemedi.");
        showLCD("Guvenlik", "Hatasi");
        delay(1000);
        gateServo.write(SERVO_CLOSED_ANGLE);
        changeState(STATE_IDLE);
        showLCD("Kartinizi", "Okutun");
        break;
      }

      Serial.print("[HMAC] ");
      Serial.println(currentHmac);

      changeState(STATE_API);
      break;
    }

    // ============================================================
    // STATE_API
    // ============================================================
    case STATE_API: {
      showLCD("Bakiyeye", "Yukleniyor...");

      // HMAC basariliysa API POST edilir. Timeout veya diger HTTP hatalarinda
      // sendToAPI false doner ve kullaniciya RED mantigi uygulanir.
      bool apiSuccess = sendToAPI(
        currentRfidUid,
        currentPoints,
        currentUnixTimestamp,
        currentHmac
      );

      if (apiSuccess) {
        Serial.println("[API] Islem basarili.");
        showLCD("Hesaba", "Yuklendi");

        // Islem tamamlandiginda mekanizma kapanir.
        gateServo.write(SERVO_CLOSED_ANGLE);

        // 3 saniye boyunca basari mesajini gostermek icin FINISH state'i kullanilir.
        finishStartedAt = millis();
        changeState(STATE_FINISH);
      } else {
        // Ag/API hatasi sistemi kilitlemez. Kullaniciya basarisiz sonuc donulur.
        Serial.println("[API] Islem basarisiz -> RED.");
        showLCD("Yukleme Hatasi", "Tekrar deneyin");
        sendPiCommand("RED");
        gateServo.write(SERVO_CLOSED_ANGLE);
        delay(1500);
        changeState(STATE_IDLE);
        showLCD("Kartinizi", "Okutun");
      }

      break;
    }

    // ============================================================
    // STATE_FINISH
    // ============================================================
    case STATE_FINISH: {
      // Basarili islemin LCD'de 3 saniye gorunmesini saglar.
      if (millis() - finishStartedAt >= 3000) {
        // Islem verilerini sifirlayarak sonraki kullanici icin temiz bir
        // state baslatiriz.
        currentRfidUid = "";
        currentWeightGrams = 0.0f;
        currentPoints = 0.0f;
        currentUnixTimestamp = 0;
        currentHmac = "";

        changeState(STATE_IDLE);
        showLCD("Kartinizi", "Okutun");
      }

      break;
    }
  }

  // Ana loop'un cok sik donerek CPU'yu gereksiz tuketmesini azaltir.
  // delay cok kisa oldugu icin UART/RFID isleyisi genel olarak responsive kalir.
  delay(5);
}