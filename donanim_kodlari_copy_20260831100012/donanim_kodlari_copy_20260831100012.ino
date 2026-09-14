#include <Wire.h>
#include <math.h>
#include <SoftwareSerial.h>
#include <string.h>

#define GPS_RX 8
#define GPS_TX 9
SoftwareSerial gpsSerial(GPS_RX, GPS_TX);
#define GPS_BAUD 9600 
#define SDA_PIN A4
#define SCL_PIN A5

const int MPU_ADDR = 0x68;
const int MAG_ADDR = 0x1E;

volatile bool mpuVeriHazir = false; 

// --- RAM DOSTU C-STRING (BELLEK ŞİŞMESİNE SON) ---
char nmeaBuffer[120];
int nmeaIndex = 0;

char eskiEnlem[15] = "";
char eskiBoylam[15] = "";
char eskiRakim[10] = "";
char eskiUydu[5] = "";
char aktifUcusModu[20] = "NORMAL";

unsigned long eskiZaman = 0; 
unsigned long sonFiltreZamani = 0;
unsigned long sonPusulaZamani = 0;

float roll = 0.0, pitch = 0.0, yaw = 0.0;  
// Pusula Kalibrasyon (Hard-Iron) Offset Değerleri
float magX_offset = 78.5; 
float magY_offset = -15.5;
float magZ_offset = 27.5;

float gyroX_offset = 0.0, gyroY_offset = 0.0, gyroZ_offset = 0.0;
float accX_offset = 0.0, accY_offset = 0.0, accZ_offset = 0.0;

int16_t ax, ay, az, gx, gy, gz; 
int16_t mx = 0, my = 0, mz = 0; 

int mpuHataSayaci = 0; // Kalp masajı sayacı

void mpuISR(){
  mpuVeriHazir = true; 
}

// --- I2C BUS CLEAR ALGORİTMASI ---
void I2C_ClearBus() {
  Wire.end();
  pinMode(SDA_PIN, INPUT_PULLUP);
  pinMode(SCL_PIN, INPUT_PULLUP);
  
  if (digitalRead(SDA_PIN) == LOW) {
    pinMode(SCL_PIN, OUTPUT);
    for (byte i = 0; i < 16; i++) {
      digitalWrite(SCL_PIN, LOW);
      delayMicroseconds(20);
      digitalWrite(SCL_PIN, HIGH);
      delayMicroseconds(20);
      if (digitalRead(SDA_PIN) == HIGH) {
        break;
      }
    }
  }
  Wire.begin();
  Wire.setWireTimeout(25000, true); 
}

void mpuKurulum() {
  Wire.beginTransmission(MAG_ADDR);
  Wire.write(0x00); 
  Wire.write(0x70); 
  Wire.endTransmission(true);

  Wire.beginTransmission(MAG_ADDR);
  Wire.write(0x01); 
  Wire.write(0xA0); 
  Wire.endTransmission(true);

  Wire.beginTransmission(MAG_ADDR);
  Wire.write(0x02); 
  Wire.write(0x01); 
  Wire.endTransmission(true);
  delay(10);

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B); 
  Wire.write(1 << 7); // MPU Reset
  Wire.endTransmission(true);
  delay(50);

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);     
  Wire.write(0);      // MPU Uyandır
  Wire.endTransmission(true);

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x1A); 
  Wire.write(0x04);   // DLPF Filtre
  Wire.endTransmission(true);

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x19); 
  Wire.write(0x09);   // Örnekleme Hızı
  Wire.endTransmission(true);

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x37); 
  Wire.write(0x02);   // Interrupt Pin Ayarı
  Wire.endTransmission(true);
  
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x38); 
  Wire.write(0x01);   // Interrupt Aktif
  Wire.endTransmission(true);
}

void mpuKalibrasyon() {
  int kalibrasyon_sayisi = 500;
  float top_ax = 0, top_ay = 0, top_az = 0;
  float top_gx = 0, top_gy = 0, top_gz = 0;

  for (int i = 0; i < kalibrasyon_sayisi; i++) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x3B);
    Wire.endTransmission(true);
    Wire.requestFrom(MPU_ADDR, 14, true);

    int16_t ham_ax = (Wire.read() << 8 | Wire.read());
    int16_t ham_ay = (Wire.read() << 8 | Wire.read());
    int16_t ham_az = (Wire.read() << 8 | Wire.read());
    Wire.read(); Wire.read();
    int16_t ham_gx = (Wire.read() << 8 | Wire.read());
    int16_t ham_gy = (Wire.read() << 8 | Wire.read());
    int16_t ham_gz = (Wire.read() << 8 | Wire.read());

    top_ax += (ham_ax / 16384.0);
    top_ay += (ham_ay / 16384.0);
    top_az += (ham_az / 16384.0);
    top_gx += (ham_gx / 131.0);
    top_gy += (ham_gy / 131.0);
    top_gz += (ham_gz / 131.0);

    delay(3); 
  }

  accX_offset = top_ax / kalibrasyon_sayisi;
  accY_offset = top_ay / kalibrasyon_sayisi;
  accZ_offset = (top_az / kalibrasyon_sayisi) - 1.0; 
  
  gyroX_offset = top_gx / kalibrasyon_sayisi;
  gyroY_offset = top_gy / kalibrasyon_sayisi;
  gyroZ_offset = top_gz / kalibrasyon_sayisi;
}


void setup() {
  memset(nmeaBuffer, 0, sizeof(nmeaBuffer)); // Buffer'ı sıfırla

  Serial.begin(115200);
  gpsSerial.begin(GPS_BAUD);

  Wire.begin();
  Wire.setWireTimeout(25000, true); 

  mpuKurulum();

  delay(500); 
  mpuKalibrasyon(); 

  pinMode(2, INPUT); 
  attachInterrupt(digitalPinToInterrupt(2), mpuISR, RISING); 
}


void komutlariKontrolEt() {
  while (Serial.available() > 0) {
    static char komutBuffer[20];
    static int komutIdx = 0;
    
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (komutIdx > 0) {
        komutBuffer[komutIdx] = '\0';
        strncpy(aktifUcusModu, komutBuffer, sizeof(aktifUcusModu) - 1);
        komutIdx = 0;
      }
    } else {
      if (komutIdx < sizeof(komutBuffer) - 1) {
        komutBuffer[komutIdx++] = c;
      }
    }
  }
}

// Özel güvenli NMEA Ayrıştırıcı (strtok kullanmadan bellek dostu yöntem)
void parseGPGGA() {
    char *p = nmeaBuffer;
    int virgulSayisi = 0;
    
    char *enlem = NULL, *enlemYonu = NULL, *boylam = NULL, *boylamYonu = NULL, *uydu = NULL, *rakim = NULL;
    
    while (*p != '\0') {
        if (*p == ',') {
            *p = '\0'; 
            virgulSayisi++;
            p++;
            
            if (virgulSayisi == 2) enlem = p;
            else if (virgulSayisi == 3) enlemYonu = p;
            else if (virgulSayisi == 4) boylam = p;
            else if (virgulSayisi == 5) boylamYonu = p;
            else if (virgulSayisi == 7) uydu = p;
            else if (virgulSayisi == 9) rakim = p;
        } else {
            p++;
        }
    }

    if (enlem && boylam && uydu && rakim) {
        if (strcmp(enlem, eskiEnlem) != 0 || strcmp(boylam, eskiBoylam) != 0 || 
            strcmp(rakim, eskiRakim) != 0 || strcmp(uydu, eskiUydu) != 0) {
            
            Serial.print("GPS,");
            if (enlemYonu && enlemYonu[0] == 'S') Serial.print("-"); else Serial.print("+");
            Serial.print(enlem); Serial.print(",");
            
            if (boylamYonu && boylamYonu[0] == 'W') Serial.print("-"); else Serial.print("+");
            Serial.print(boylam); Serial.print(",");
            
            Serial.print(rakim); Serial.print(",");
            Serial.print(uydu); Serial.print("\n");
            
            strncpy(eskiEnlem, enlem, sizeof(eskiEnlem) - 1);
            strncpy(eskiBoylam, boylam, sizeof(eskiBoylam) - 1);
            strncpy(eskiRakim, rakim, sizeof(eskiRakim) - 1);
            strncpy(eskiUydu, uydu, sizeof(eskiUydu) - 1);
        }
    }
}


void loop() {
  komutlariKontrolEt();

  // --- 1. GPS NMEA OKUMA (NON-BLOCKING CHAR ARRAY) ---
  while (gpsSerial.available() > 0) {
    char gpsData = gpsSerial.read();
    
    if (gpsData == '\n') {
      nmeaBuffer[nmeaIndex] = '\0'; 
      if (strncmp(nmeaBuffer, "$GPGGA", 6) == 0) {
          parseGPGGA();
      }
      nmeaIndex = 0; 
    } else if (gpsData != '\r') {
      if (nmeaIndex < sizeof(nmeaBuffer) - 1) {
          nmeaBuffer[nmeaIndex++] = gpsData;
      } else {
          nmeaIndex = 0; 
      }
    }
  } 

  // --- 2. MPU6050 & HMC5883L OKUMA (ZAMANLAYICI MİMARİSİ) ---
  if (mpuVeriHazir || digitalRead(2) == HIGH) { 
    mpuVeriHazir = false; 
    unsigned long suAn = millis();
    float dt = (suAn - sonFiltreZamani) / 1000.0;
    sonFiltreZamani = suAn;

    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x3B);
    Wire.endTransmission(true);

    if (Wire.requestFrom(MPU_ADDR, 14, true) == 14) {
       mpuHataSayaci = 0; // Okuma başarılı, sayacı sıfırla

       ax = (Wire.read() << 8 | Wire.read());
       ay = (Wire.read() << 8 | Wire.read());
       az = (Wire.read() << 8 | Wire.read());

       int16_t tempRaw = (Wire.read() << 8 | Wire.read());
       float sicaklikC = (tempRaw / 340.0) + 36.53;

       gx = (Wire.read() << 8 | Wire.read());
       gy = (Wire.read() << 8 | Wire.read());
       gz = (Wire.read() << 8 | Wire.read());

       if (suAn - sonPusulaZamani >= 100) {
           sonPusulaZamani = suAn;

           Wire.beginTransmission(MAG_ADDR);
           Wire.write(0x03); 
           Wire.endTransmission(true); 
           
           Wire.requestFrom(MAG_ADDR, 6, true);
           if (Wire.available() >= 6) {
               mx = (Wire.read() << 8 | Wire.read());
               mz = (Wire.read() << 8 | Wire.read()); 
               my = (Wire.read() << 8 | Wire.read());
           }

           Wire.beginTransmission(MAG_ADDR);
           Wire.write(0x02);
           Wire.write(0x01); 
           Wire.endTransmission(true);
       }

       float gercek_ax = (ax / 16384.0) - accX_offset;
       float gercek_ay = (ay / 16384.0) - accY_offset;
       float gercek_az = (az / 16384.0) - accZ_offset;

       float gercek_gx = (gx / 131.0) - gyroX_offset;
       float gercek_gy = (gy / 131.0) - gyroY_offset;
       float gercek_gz = (gz / 131.0) - gyroZ_offset;

       float toplamG = sqrt((gercek_ax * gercek_ax) + (gercek_ay * gercek_ay) + (gercek_az * gercek_az));
       if (toplamG < 0.2) {
         strncpy(aktifUcusModu, "FREE_FALL", sizeof(aktifUcusModu)-1);
       }
       else if (toplamG > 3.0) {
         strncpy(aktifUcusModu, "CRASH", sizeof(aktifUcusModu)-1);
       }

       float accRoll = atan(gercek_ay / (sqrt((gercek_ax * gercek_ax) + (gercek_az * gercek_az))+0.0001)) * 180 / PI;
       float accPitch = atan(-1 * gercek_ax / (sqrt((gercek_ay * gercek_ay) + (gercek_az * gercek_az))+0.0001)) * 180 / PI;

       roll = 0.96 * (roll + gercek_gx * dt) + 0.04 * accRoll;
       pitch = 0.96 * (pitch + gercek_gy * dt) + 0.04 * accPitch;
       // --- NaN KORUMASI (OTONOM KURTARMA) ---
       if (isnan(roll) || isnan(pitch)) {
           roll = 0.0;
           pitch = 0.0;
       }
       
       // --- 1. HARD-IRON (SABİT MIKNATISLANMA) TEMİZLİĞİ ---
       float cal_mx = mx - magX_offset;
       float cal_my = my - magY_offset;
       float cal_mz = mz - magZ_offset;

       // --- 2. EĞİKLİK TELAFİSİ (TILT COMPENSATION) ---
       float rollRad = roll * PI / 180.0;
       float pitchRad = pitch * PI / 180.0;

       float cosRoll = cos(rollRad);
       float sinRoll = sin(rollRad);
       float cosPitch = cos(pitchRad);
       float sinPitch = sin(pitchRad);

       // Pusulayı sanal olarak yere paralel hale getiriyoruz
       float Xh = cal_mx * cosPitch + cal_mz * sinPitch;
       float Yh = cal_mx * sinRoll * sinPitch + cal_my * cosRoll - cal_mz * sinRoll * cosPitch;

       // --- 3. GERÇEK KUZEY (TRUE NORTH) HESAPLAMASI ---
       yaw = atan2(Yh, Xh) * 180.0 / PI;
       
       // Türkiye için yaklaşık +5.5 derece Manyetik Sapma (Magnetic Declination) eklenir
       yaw += 5.5; 
    
       if (yaw > 180.0) yaw -= 360.0;
       else if (yaw < -180.0) yaw += 360.0;
       
       // --- YERÇEKİMİNİ DİNAMİK OLARAK SİLME (LİNEER İVME HESAPLAMASI) ---
       // Euler açılarını (Roll ve Pitch) kullanarak yerçekimi vektörünü 3 eksende hesaplıyoruz
       float grav_x = sin(pitch * PI / 180.0);
       float grav_y = -sin(roll * PI / 180.0) * cos(pitch * PI / 180.0);
       float grav_z = cos(roll * PI / 180.0) * cos(pitch * PI / 180.0);

       // Ham ivmeden yerçekimi vektörünü çıkararak sadece uçağın "Gerçek/Lineer İvmesini" buluyoruz
       float lineer_ax = gercek_ax - grav_x;
       float lineer_ay = gercek_ay - grav_y;
       float lineer_az = gercek_az - grav_z;

       if (suAn - eskiZaman >= 100) {
           eskiZaman = suAn; 

           Serial.print("MPU,");
           Serial.print(suAn);            Serial.print(",");
           Serial.print(lineer_ax, 3);    Serial.print(",");
           Serial.print(lineer_ay, 3);    Serial.print(",");
           Serial.print(lineer_az, 3);    Serial.print(",");
           Serial.print(gercek_gx, 2);    Serial.print(",");
           Serial.print(gercek_gy, 2);    Serial.print(",");
           Serial.print(gercek_gz, 2);    Serial.print(",");
           Serial.print(sicaklikC, 2);    Serial.print(",");
           Serial.print(roll, 2);         Serial.print(",");
           Serial.print(pitch, 2);        Serial.print(",");
           Serial.print(yaw, 2);          Serial.print(",");
           Serial.print(mx);              Serial.print(",");
           Serial.print(my);              Serial.print(",");
           Serial.print(mz);
           Serial.print("\n"); 
       }
    } else {
        // --- SENSÖR KİLİTLENDİ (OKUMA BAŞARISIZ) ---
        mpuHataSayaci++;
        if (mpuHataSayaci > 5) {
            Serial.println("[BİLGİ] MPU6050 Kilitlendi (I2C Hata)! Otonom Kurtarma (Kalp Masaji) Uygulaniyor...");
            I2C_ClearBus(); 
            delay(10);
            mpuKurulum();   
            mpuHataSayaci = 0;
            Serial.println("[BİLGİ] MPU6050 Yeniden Baslatildi ve Ucus Kurtarildi!");
        }
    }
  } else if (millis() - sonFiltreZamani > 500) {
      // SENSÖR TAMAMEN DONDU, KESME (INTERRUPT) SİNYALİ ÜRETMİYOR!
      Serial.println("[BİLGİ] MPU6050'den Sinyal Kesildi (Interrupt Dondu)! Acil Kurtarma Uygulaniyor...");
      I2C_ClearBus(); 
      delay(10);
      mpuKurulum();
      sonFiltreZamani = millis(); // Bekleme sayacını sıfırla ki ard arda reset atmasın
      Serial.println("[BİLGİ] MPU6050 Hayata Döndürüldü!");
  }
}
