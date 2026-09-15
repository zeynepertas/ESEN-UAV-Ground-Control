#include <Wire.h>
#include <math.h>
#include <SoftwareSerial.h>
#include <string.h>
#include <avr/wdt.h>

#define GPS_RX 8
#define GPS_TX 9
#define SDA_PIN A4
#define SCL_PIN A5
#define MPU_ADDR 0x68
#define MAG_ADDR 0x1E
#define GPS_BAUD 9600

// ==========================================
// 1. I2C KONTROL VE KURTARMA SINIFI (I2CHelper)
// ==========================================
class I2CHelper {
public:
    static void clearBus() {
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
};

// ==========================================
// 2. MPU6050 & HMC5883L (IMU) SINIFI (MPUManager)
// ==========================================
class MPUManager {
public:
    volatile bool veriHazir = false;
    unsigned long sonFiltreZamani = 0;
    unsigned long sonPusulaZamani = 0;
    int hataSayaci = 0;
    
    float roll = 0.0, pitch = 0.0, yaw = 0.0;  
    float magX_offset = 78.5, magY_offset = -15.5, magZ_offset = 27.5;
    float gyroX_offset = 0.0, gyroY_offset = 0.0, gyroZ_offset = 0.0;
    float accX_offset = 0.0, accY_offset = 0.0, accZ_offset = 0.0;
    
    int16_t ax, ay, az, gx, gy, gz, mx = 0, my = 0, mz = 0; 
    float lineer_ax = 0, lineer_ay = 0, lineer_az = 0;
    float sicaklikC = 0;
    char ucusModu[20] = "NORMAL";

    void begin() {
        kurulum();
        delay(500);
        kalibreEt();
    }

    void kurulum() {
        Wire.beginTransmission(MAG_ADDR);
        Wire.write(0x00); Wire.write(0x70); 
        Wire.endTransmission(true);

        Wire.beginTransmission(MAG_ADDR);
        Wire.write(0x01); Wire.write(0xA0); 
        Wire.endTransmission(true);

        Wire.beginTransmission(MAG_ADDR);
        Wire.write(0x02); Wire.write(0x01); 
        Wire.endTransmission(true);
        delay(10);

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x6B); Wire.write(1 << 7); // MPU Reset
        Wire.endTransmission(true);
        delay(50);

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x6B); Wire.write(0);      // Uyandır
        Wire.endTransmission(true);

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x1A); Wire.write(0x04);   // DLPF Filtre
        Wire.endTransmission(true);

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x19); Wire.write(0x09);   // Örnekleme Hızı
        Wire.endTransmission(true);

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x37); Wire.write(0x02);   // Interrupt Pin Ayarı
        Wire.endTransmission(true);
        
        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x38); Wire.write(0x01);   // Interrupt Aktif
        Wire.endTransmission(true);
    }

    void kalibreEt() {
        int kalibrasyon_sayisi = 500;
        float top_ax = 0, top_ay = 0, top_az = 0;
        float top_gx = 0, top_gy = 0, top_gz = 0;

        for (int i = 0; i < kalibrasyon_sayisi; i++) {
            Wire.beginTransmission(MPU_ADDR);
            Wire.write(0x3B);
            Wire.endTransmission(true);
            Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)14, (uint8_t)true);

            top_ax += (int16_t(Wire.read() << 8 | Wire.read()) / 16384.0);
            top_ay += (int16_t(Wire.read() << 8 | Wire.read()) / 16384.0);
            top_az += (int16_t(Wire.read() << 8 | Wire.read()) / 16384.0);
            Wire.read(); Wire.read();
            top_gx += (int16_t(Wire.read() << 8 | Wire.read()) / 131.0);
            top_gy += (int16_t(Wire.read() << 8 | Wire.read()) / 131.0);
            top_gz += (int16_t(Wire.read() << 8 | Wire.read()) / 131.0);
            delay(3); 
        }

        accX_offset = top_ax / kalibrasyon_sayisi;
        accY_offset = top_ay / kalibrasyon_sayisi;
        accZ_offset = (top_az / kalibrasyon_sayisi) - 1.0; 
        
        gyroX_offset = top_gx / kalibrasyon_sayisi;
        gyroY_offset = top_gy / kalibrasyon_sayisi;
        gyroZ_offset = top_gz / kalibrasyon_sayisi;
        
        // Filtre zamanlayıcısını güncelle ki 1.5 saniyelik kalibrasyon süresi 'dt' değerini bozmasın
        sonFiltreZamani = millis();
    }

    bool okuVeHesapla() {
        if (!veriHazir && digitalRead(2) == LOW) return false;
        
        veriHazir = false;
        unsigned long suAn = millis();
        
        // --- DT (ZAMAN FARKI) GÜVENLİK FİLTRESİ ---
        float dt = 0.005; // Varsayılan 5ms
        if (suAn > sonFiltreZamani) {
            dt = (suAn - sonFiltreZamani) / 1000.0;
            if (dt > 0.1) dt = 0.1; // Maksimum 100ms sınırı (Büyük sıçramaları engeller)
        }
        sonFiltreZamani = suAn;

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x3B);
        Wire.endTransmission(true);

        if (Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)14, (uint8_t)true) == 14) {
            hataSayaci = 0; 
            ax = (Wire.read() << 8 | Wire.read());
            ay = (Wire.read() << 8 | Wire.read());
            az = (Wire.read() << 8 | Wire.read());

            int16_t tempRaw = (Wire.read() << 8 | Wire.read());
            sicaklikC = (tempRaw / 340.0) + 36.53;

            gx = (Wire.read() << 8 | Wire.read());
            gy = (Wire.read() << 8 | Wire.read());
            gz = (Wire.read() << 8 | Wire.read());

            if (suAn - sonPusulaZamani >= 100) {
                sonPusulaZamani = suAn;
                Wire.beginTransmission(MAG_ADDR);
                Wire.write(0x03); 
                Wire.endTransmission(true); 
                Wire.requestFrom((uint8_t)MAG_ADDR, (uint8_t)6, (uint8_t)true);
                if (Wire.available() >= 6) {
                    mx = (Wire.read() << 8 | Wire.read());
                    mz = (Wire.read() << 8 | Wire.read()); 
                    my = (Wire.read() << 8 | Wire.read());
                }
                Wire.beginTransmission(MAG_ADDR);
                Wire.write(0x02); Wire.write(0x01); 
                Wire.endTransmission(true);
            }

            // Hesaplamalar
            float gercek_ax = (ax / 16384.0) - accX_offset;
            float gercek_ay = (ay / 16384.0) - accY_offset;
            float gercek_az = (az / 16384.0) - accZ_offset;
            float gercek_gx = (gx / 131.0) - gyroX_offset;
            float gercek_gy = (gy / 131.0) - gyroY_offset;
            float gercek_gz = (gz / 131.0) - gyroZ_offset;

            float toplamG = sqrt((gercek_ax * gercek_ax) + (gercek_ay * gercek_ay) + (gercek_az * gercek_az));
            if (toplamG < 0.2) strncpy(ucusModu, "FREE_FALL", 19);
            else if (toplamG > 3.0) strncpy(ucusModu, "CRASH", 19);

            float accRoll = atan(gercek_ay / (sqrt((gercek_ax * gercek_ax) + (gercek_az * gercek_az))+0.0001)) * 180 / PI;
            float accPitch = atan(-1 * gercek_ax / (sqrt((gercek_ay * gercek_ay) + (gercek_az * gercek_az))+0.0001)) * 180 / PI;

            roll = 0.96 * (roll + gercek_gx * dt) + 0.04 * accRoll;
            pitch = 0.96 * (pitch + gercek_gy * dt) + 0.04 * accPitch;
            
            if (isnan(roll) || isnan(pitch)) { roll = 0.0; pitch = 0.0; }
            
            float cal_mx = mx - magX_offset;
            float cal_my = my - magY_offset;
            float cal_mz = mz - magZ_offset;

            float rollRad = roll * PI / 180.0;
            float pitchRad = pitch * PI / 180.0;

            float Xh = cal_mx * cos(pitchRad) + cal_mz * sin(pitchRad);
            float Yh = cal_mx * sin(rollRad) * sin(pitchRad) + cal_my * cos(rollRad) - cal_mz * sin(rollRad) * cos(pitchRad);

            yaw = atan2(Yh, Xh) * 180.0 / PI;
            yaw += 5.5; 
            if (yaw > 180.0) yaw -= 360.0;
            else if (yaw < -180.0) yaw += 360.0;
            
            float grav_x = sin(pitch * PI / 180.0);
            float grav_y = -sin(roll * PI / 180.0) * cos(pitch * PI / 180.0);
            float grav_z = cos(roll * PI / 180.0) * cos(pitch * PI / 180.0);

            lineer_ax = gercek_ax - grav_x;
            lineer_ay = gercek_ay - grav_y;
            lineer_az = gercek_az - grav_z;
            
            return true;
        } else {
            handleError();
            return false;
        }
    }

    void handleError() {
        hataSayaci++;
        if (hataSayaci > 5) {
            Serial.println("[BİLGİ] MPU6050 Kilitlendi (I2C Hata)! Otonom Kurtarma Uygulaniyor...");
            I2CHelper::clearBus(); 
            delay(10);
            kurulum();   
            hataSayaci = 0;
            Serial.println("[BİLGİ] MPU6050 Yeniden Baslatildi!");
        }
    }
    
    void checkTimeout() {
        if (millis() - sonFiltreZamani > 500) {
            Serial.println("[BİLGİ] MPU6050'den Sinyal Kesildi (Interrupt Dondu)!");
            I2CHelper::clearBus(); 
            delay(10);
            kurulum();
            sonFiltreZamani = millis(); 
        }
    }
};

// ==========================================
// 3. GPS SINIFI (GPSManager)
// ==========================================
class GPSManager {
private:
    char nmeaBuffer[120];
    int nmeaIndex = 0;
    char eskiEnlem[15] = "", eskiBoylam[15] = "", eskiRakim[10] = "", eskiUydu[5] = "";
    SoftwareSerial* serial;

public:
    GPSManager(SoftwareSerial* serialPort) {
        this->serial = serialPort;
        memset(nmeaBuffer, 0, sizeof(nmeaBuffer));
    }

    void begin() {
        serial->begin(GPS_BAUD);
    }

    void guncelle() {
        while (serial->available() > 0) {
            char gpsData = serial->read();
            if (gpsData == '\n') {
                nmeaBuffer[nmeaIndex] = '\0'; 
                if (strncmp(nmeaBuffer, "$GPGGA", 6) == 0) {
                    ayristir();
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
    }

private:
    void ayristir() {
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
            if (strcmp(enlem, eskiEnlem) != 0 || strcmp(boylam, eskiBoylam) != 0) {
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
};

// ==========================================
// 4. SİSTEM KOMUT YÖNETİCİSİ (CommandProcessor)
// ==========================================
class CommandProcessor {
public:
    static void check(MPUManager& mpu) {
        while (Serial.available() > 0) {
            static char buffer[20];
            static int idx = 0;
            
            char c = Serial.read();
            if (c == '\n' || c == '\r') {
                if (idx > 0) {
                    buffer[idx] = '\0';
                    if (strcmp(buffer, "CALIBRATE") == 0) {
                        Serial.println("[BİLGİ] Kalibrasyon Komutu Alindi!");
                        mpu.kalibreEt();
                        Serial.println("[BİLGİ] Kalibrasyon Tamamlandi! Algoritma dogal olarak sifirlanacak.");
                    } else {
                        strncpy(mpu.ucusModu, buffer, 19);
                    }
                    idx = 0;
                }
            } else {
                if (idx < sizeof(buffer) - 1) {
                    buffer[idx++] = c;
                }
            }
        }
    }
};

// ==========================================
// GLOBAL NESNELER VE ANA DÖNGÜ
// ==========================================
SoftwareSerial gpsPort(GPS_RX, GPS_TX);
GPSManager gps(&gpsPort);
MPUManager mpu;
unsigned long eskiZaman = 0;

void mpuISR(){
    mpu.veriHazir = true;
}

void setup() {
    Serial.begin(115200);
    gps.begin();

    Wire.begin();
    Wire.setWireTimeout(25000, true); 

    mpu.begin();

    pinMode(2, INPUT); 
    attachInterrupt(digitalPinToInterrupt(2), mpuISR, RISING);

    wdt_enable(WDTO_2S);
}

void loop() {
    wdt_reset(); 
    CommandProcessor::check(mpu);
    gps.guncelle();

    if (mpu.okuVeHesapla()) {
        unsigned long suAn = millis();
        if (suAn - eskiZaman >= 100) {
            eskiZaman = suAn; 
            Serial.print("MPU,");
            Serial.print(suAn);            Serial.print(",");
            Serial.print(mpu.lineer_ax, 3);    Serial.print(",");
            Serial.print(mpu.lineer_ay, 3);    Serial.print(",");
            Serial.print(mpu.lineer_az, 3);    Serial.print(",");
            Serial.print(mpu.gx/131.0 - mpu.gyroX_offset, 2);    Serial.print(",");
            Serial.print(mpu.gy/131.0 - mpu.gyroY_offset, 2);    Serial.print(",");
            Serial.print(mpu.gz/131.0 - mpu.gyroZ_offset, 2);    Serial.print(",");
            Serial.print(mpu.sicaklikC, 2);    Serial.print(",");
            Serial.print(mpu.roll, 2);         Serial.print(",");
            Serial.print(mpu.pitch, 2);        Serial.print(",");
            Serial.print(mpu.yaw, 2);          Serial.print(",");
            Serial.print(mpu.mx);              Serial.print(",");
            Serial.print(mpu.my);              Serial.print(",");
            Serial.print(mpu.mz);
            Serial.print("\n"); 
        }
    } else {
        mpu.checkTimeout();
    }
}
