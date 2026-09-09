#include <Wire.h>//12c haberlesme kütüphanesi
#include <math.h>
#include <SoftwareSerial.h>//GPS iletişimi için sanal seri port kütüphanesi
#define GPS_RX 8
#define GPS_TX 9//Yeni GPS Pinleri (Arduino Uno/Nano için):
SoftwareSerial gpsSerial(GPS_RX, GPS_TX);
#define GPS_BAUD 9600 //konusma hizi

// Kesme (Interrupt) bayrağı: MPU'dan sinyal geldiğinde bu True olacak
volatile bool mpuVeriHazir = false;//sensörün "yeni veri var" diye bağırdığı (Interrupt) anlarda tetiklenen bir alarm bayrağı

String eskiEnlem = "";//onceki degerleri hatirlamak icin hafiza degiskenleri(gps)
String eskiBoylam = "";
String eskiRakim = "";
String eskiUydu = "";

unsigned long eskiZaman = 0; // Kronometre hafızası mpu zamanlayicisi icin
unsigned long sonFiltreZamani = 0;
unsigned long sonPusulaZamani = 0;
float roll = 0.0;
float pitch = 0.0;
float yaw = 0.0; // YAW: İHA'nın Z ekseni etrafındaki yönelmesi
float baslangicYaw = 0.0; // Göreceli pusula için sıfır noktası hafızası
bool pusulaKalibreEdildi = false;

// --- KALİBRASYON OFFSET DEĞİŞKENLERİ ---
float gyroX_offset = 0.0, gyroY_offset = 0.0, gyroZ_offset = 0.0;
float accX_offset = 0.0, accY_offset = 0.0, accZ_offset = 0.0;

const int MPU_ADDR = 0x68;//mpunun 12c adresi
int16_t ax, ay, az, gx, gy, gz;//ivme ve jireskop verileri 16 bit

const int MAG_ADDR = 0x1E; // HMC5883L I2C adresi
int16_t mx = 0, my = 0, mz = 0; // Manyetik alan verileri



// Fonksiyon prototipi (Derleyiciye önceden haber veriyoruz)
void mpuISR(){
  mpuVeriHazir = true; // Sadece bayrağı kaldırıp hemen ana döngüye dönüyoruz
};

// İHA'nın anlık otopilot modu hafızası
String aktifUcusModu = "NORMAL";


//Sistem açıldığında masada düz dururken MPU6050'den 500 tane ham örnek alır. Sensör düz durduğu halde ivme 0 değilse veya dönmediği halde jiroskop 0 değilse, aradaki farkı hesaplayıp "Offset (Hata Payı)" değişkenlerine kaydeder
void mpuKalibrasyon() {
  Serial.println("========================================");
  Serial.println("[KALİBRASYON] MPU6050 Kalibre ediliyor...");
  Serial.println("[DİKKAT] Cihazi MASADA DÜZ ve HAREKETSİZ tutun! (3 Saniye)");
  
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
    int16_t ham_temp = (Wire.read() << 8 | Wire.read()); // Sıcaklığı atla
    int16_t ham_gx = (Wire.read() << 8 | Wire.read());
    int16_t ham_gy = (Wire.read() << 8 | Wire.read());
    int16_t ham_gz = (Wire.read() << 8 | Wire.read());

    // Ham verileri g ve derece/sn cinsine çevirip toplama ekle
    top_ax += (ham_ax / 16384.0);
    top_ay += (ham_ay / 16384.0);
    top_az += (ham_az / 16384.0);
    top_gx += (ham_gx / 131.0);
    top_gy += (ham_gy / 131.0);
    top_gz += (ham_gz / 131.0);

    delay(3); // Sensörün nefes alması için 3ms bekle
  }

  // Ortalamaları bularak kalıcı offset (hata) değerlerine yaz
  accX_offset = top_ax / kalibrasyon_sayisi;
  accY_offset = top_ay / kalibrasyon_sayisi;
  
  // Z ekseni yerçekimi olduğu için düz durduğunda 1.0 okumalıdır. Farkı alıyoruz.
  accZ_offset = (top_az / kalibrasyon_sayisi) - 1.0; 
  
  gyroX_offset = top_gx / kalibrasyon_sayisi;
  gyroY_offset = top_gy / kalibrasyon_sayisi;
  gyroZ_offset = top_gz / kalibrasyon_sayisi;

  Serial.println("[KALİBRASYON] Tamamlandi! Cihaz ucus icin hazir.");
  Serial.println("========================================");
}


void setup() {//cihaza güç verildiğinde sadece 1 kez çalışır
  //gps setup kodu
  Serial.begin(115200);
  gpsSerial.begin(GPS_BAUD);//gps ve esp koprusu
  Serial.println("Serial 2 started at 9600 baud rate");

 //mpu setup kodu
  Wire.begin();//12c haberlesmesi baslar
  Wire.setWireTimeout(3000, true); // I2C kilitlenmelerini önlemek için 3 milisaniye zaman aşımı ekle
  Serial.begin(115200);

  // --- MANYETOMETRE (HMC5883L) KURULUMU ---
  // Çin malı HMC5883L klonlarının donmasını önlemek için Güvenli Başlatma
  Wire.beginTransmission(MAG_ADDR);
  Wire.write(0x00); // Config A Register
  Wire.write(0x70); // 8-örnekleme ortalaması, 15 Hz
  Wire.endTransmission(true);

  Wire.beginTransmission(MAG_ADDR);
  Wire.write(0x01); // Config B Register
  Wire.write(0xA0); // Gain (Kazanç) Ayarı
  Wire.endTransmission(true);

  Wire.beginTransmission(MAG_ADDR);
  Wire.write(0x02); // Mod Register (HMC5883L)
  Wire.write(0x01); // SİNGLE-MEASUREMENT (Tekli Ölçüm) MODU! Kilitlenmeyi kökten çözer.
  Wire.endTransmission(true);
  delay(100);

  Wire.beginTransmission(MPU_ADDR); //Sensorun kapisini caldik
  Wire.write(0x6B);//register sectik
  Wire.write(1 << 7);//reset attik
  Wire.endTransmission(true);//baglantiyi kapat is bitti

  delay(100);

// ... (setup içindeki mevcut kodlar)
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);     // Tekrar register seç
  Wire.write(0);        // 0 yazarak uykuyu kapat, çalışmaya başla
  Wire.endTransmission(true);




 //Sensörün beynindeki 0x1A adresine gidip filtre seviyesini 0x04 yapıyoruz. 
 //Bu sayede sensör saniyede 21 Hz'den daha hızlı gerçekleşen tüm mikro titreşimleri "Bunlar motor ve pervane gürültüsüdür" deyip daha ana karta yollamadan donanım seviyesinde filtreleyip silecek.
    // --- MPU6050 DONANIMSAL FİLTRE (DLPF) AYARI ---
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x1A); // CONFIG Register'ı (Filtre ayarlarının olduğu donanım adresi)
  Wire.write(0x04); // 0x04 değeri: 21 Hz filtreleme (Yüksek frekanslı motor/pervane titreşimlerini siler)
  Wire.endTransmission(true);


  // MPU UYANDIKTAN HEMEN SONRA KALİBRASYONU ÇAĞIR:
  delay(500); // Sensör kendine gelsin diye yarım saniye bekle
  mpuKalibrasyon();

  // --- INTERRUPT (KESME) TANIMLAMASI ---
  pinMode(2, INPUT); 
  attachInterrupt(digitalPinToInterrupt(2), mpuISR, RISING); // SİLİNMEMESİ GEREKEN KOMUT

    // MPU6050 Kesme (Interrupt) Ayarları
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x37); // INT Pin konfigürasyon registerı
  Wire.write(0x02); // INT pini aktifken YÜKSEK (HIGH) olsun
  Wire.endTransmission(true);
  
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x38); // Interrupt Enable (Kesme Açma) registerı
  Wire.write(0x01); // "Veri Hazır" (Data Ready) kesmesini aktif et
  Wire.endTransmission(true);

}

String nmeaSatiri="";//sifirdan baslattik



void komutlariKontrolEt() {
  if (Serial.available() > 0) {
    String gelenKomut = Serial.readStringUntil('\n');
    gelenKomut.trim();

    if (gelenKomut.length() > 0) {
      Serial.print("Merkezden Komut Geldi: ");
      Serial.println(gelenKomut);

     aktifUcusModu = gelenKomut;

      if (gelenKomut == "TAKEOFF") {
        Serial.println("-> [OTOPİLOT] Otomatik Kalkış tetiklendi!");
      } 
      else if (gelenKomut == "RTL") {
        Serial.println("-> [OTOPİLOT] Eve Dönüş (RTL) tetiklendi!");
      } 
      else if (gelenKomut == "LAND") {
        Serial.println("-> [OTOPİLOT] Dikey İniş tetiklendi!");
      } 
      else if (gelenKomut == "EMERGENCY_STOP") {
        Serial.println("-> [KRİTİK] ACİL MOTOR DURDURMA!");
      }
    }
  }
}



void loop() {//ESP32 calistigi surece sonsuza kadar doner
  komutlariKontrolEt();

  while (gpsSerial.available() > 0){//eger gps den okunacak veri varsa
    char gpsData = gpsSerial.read();//uydudan gelen karmaşık NMEA metinlerini ("$GPGGA...") harf harf okur, virgülleri sayarak Enlem, Boylam ve Rakım değerlerini cımbızla çekip alır. Değişim varsa bunu doğrudan paketler.
    nmeaSatiri+=gpsData; //data her okundugunda nmeasatiri artar
    if(gpsData=='\n'){//satir bitti mi diye kontrol
    
      if(nmeaSatiri.startsWith("$GPGGA")){
       int virgul1 = nmeaSatiri.indexOf(',');
       int virgul2 = nmeaSatiri.indexOf(',', virgul1 + 1); 
       int virgul3 = nmeaSatiri.indexOf(',', virgul2 + 1); 
       int virgul4 = nmeaSatiri.indexOf(',', virgul3 + 1);
       int virgul5 = nmeaSatiri.indexOf(',', virgul4 + 1);
       int virgul6 = nmeaSatiri.indexOf(',', virgul5 + 1);
       int virgul7 = nmeaSatiri.indexOf(',', virgul6 + 1);
       int virgul8 = nmeaSatiri.indexOf(',', virgul7 + 1);
       int virgul9 = nmeaSatiri.indexOf(',', virgul8 + 1);
       int virgul10 = nmeaSatiri.indexOf(',', virgul9 + 1);

       String enlem = nmeaSatiri.substring(virgul2 + 1, virgul3); //2-3. virgul arasi
       String boylam = nmeaSatiri.substring(virgul4 + 1, nmeaSatiri.indexOf(',', virgul4 + 1));//4-5. virgul arasi
       String uydu = nmeaSatiri.substring(virgul7 + 1, virgul8); // 7-8. virgül arası
       String rakim = nmeaSatiri.substring(virgul9 + 1, virgul10); // 9-10. virgül arası

       String enlemYonu = nmeaSatiri.substring(virgul3 + 1, virgul4); //yon harflerini(n/s ve e/w)yanlarındaki virgulden cekiyoruz
       String boylamYonu = nmeaSatiri.substring(virgul5 + 1, virgul6);

       if (enlemYonu == "S") {
           enlem = "-" + enlem;
       } else if (enlemYonu == "N") {
           enlem = "+" + enlem;
       }

       if (boylamYonu == "W") {
           boylam = "-" + boylam;
       } else if (boylamYonu == "E") {
           boylam = "+" + boylam;
       }

       if (enlem != eskiEnlem || boylam != eskiBoylam || rakim != eskiRakim || uydu != eskiUydu) {
      // GPS verisini de kablosuz olarak gönderiyoruz
      String gpsVeri = "GPS," + enlem + "," + boylam + "," + rakim + "," + uydu + "\n";
       Serial.print(gpsVeri);
       eskiEnlem = enlem;
       eskiBoylam = boylam;//ekrana yazdirdiktan sonra yeni degerleri eski olarak kaydettim
       eskiRakim = rakim;
       eskiUydu = uydu;
       }
      }
      nmeaSatiri = "";//tekrar sifirladim
    }
  } 

    //mpu loop kodu
    // --- MPU LOOP KODU (ZAMANLAYICI MİMARİSİ) ---
    if (mpuVeriHazir) { //yani interrupt tetiklenirse eğer
    mpuVeriHazir = false; // İçeri girer girmez bayrağı indir (bir sonraki kesme için bekle)
    unsigned long suAn = millis();
    float dt = (suAn - sonFiltreZamani) / 1000.0;
    sonFiltreZamani = suAn;

   Wire.beginTransmission(MPU_ADDR);
   Wire.write(0x3B);//mpu da ivme verilerinin tutuldugu ilk adresten veriyi istiyorum
   Wire.endTransmission(true);//baglantiyi kapat,

  if (Wire.requestFrom(MPU_ADDR, 14, true) == 14) {//14 baytlık veri(her biri 2 bayttan 3 ivme,3 jiroskop 1 sicaklik)


   ax = (Wire.read() << 8 | Wire.read());//önce büyük bayt, sonra kucuk bayt gelir o yuzden 8 br sola
   ay = (Wire.read() << 8 | Wire.read());//sensorda tek seferde 16 bitlik gelemez o yuzden boyle yapiyoruz
   az = (Wire.read() << 8 | Wire.read());

   int16_t tempRaw = (Wire.read() << 8 | Wire.read());//sicaklik
   float sicaklikC = (tempRaw / 340.0) + 36.53;//sicakligi celciusa cevirme formulu

   gx = (Wire.read() << 8 | Wire.read());
   gy = (Wire.read() << 8 | Wire.read());
   gz = (Wire.read() << 8 | Wire.read());

   // --- MANYETOMETRE OKUMASI (Saniyede 10 Kere / 100ms) ---
   if (suAn - sonPusulaZamani >= 100) {
       sonPusulaZamani = suAn;

       // 1. Önceki tetiğin sonucunu oku
       Wire.beginTransmission(MAG_ADDR);
       Wire.write(0x03); 
       Wire.endTransmission(true); 
       
       Wire.requestFrom(MAG_ADDR, 6, true);
       if (Wire.available() >= 6) {
           mx = (Wire.read() << 8 | Wire.read());
           mz = (Wire.read() << 8 | Wire.read()); 
           my = (Wire.read() << 8 | Wire.read());
       }

       // 2. Bir sonraki okuma için yeniden tekli ölçüm tetiği yolla!
       // Çip ölçümü yapar ve hemen uykuya dalar. I2C hattı ASLA kilitlenmez.
       Wire.beginTransmission(MAG_ADDR);
       Wire.write(0x02);
       Wire.write(0x01); // Single-Measurement
       Wire.endTransmission(true);

       // --- SIFIR KALİBRASYON (İlk Açılışta Yön Hafızası) ---
       if (!pusulaKalibreEdildi) {
           baslangicYaw = atan2(my, mx) * 180 / PI;
           pusulaKalibreEdildi = true;
           Serial.println("[PUSULA] Sifir noktasi (Kuzey) ayarlandi!");
       }
   }

      float gercek_ax = (ax / 16384.0) - accX_offset;//ivme verilerini g cinsine kalibrasyon ediyorum ve hata payını çıkarıyorum
      float gercek_ay = (ay / 16384.0) - accY_offset;
      float gercek_az = (az / 16384.0) - accZ_offset;

      float gercek_gx = (gx / 131.0) - gyroX_offset;//jiroskop verilereini derece/saniye cinsine ceviriyorum ve hata payını çıkarıyorum
      float gercek_gy = (gy / 131.0) - gyroY_offset;
      float gercek_gz = (gz / 131.0) - gyroZ_offset;


     // --- KAZA VE DÜŞÜŞ ALGILAMA ---
      float toplamG = sqrt(pow(gercek_ax, 2) + pow(gercek_ay, 2) + pow(gercek_az, 2));
      if (toplamG < 0.2) {
        Serial.println("!!! [ALARM] SERBEST DÜŞÜŞ TESPİT EDİLDİ !!!");
        aktifUcusModu = "FREE_FALL";
      }
      else if (toplamG > 3.0) {
        Serial.println("!!! [KRİTİK] ÇARPIŞMA/KIRIM TESPİT EDİLDİ !!!");
        aktifUcusModu = "CRASH";
      }


      // --- TAMAMLAYICI FİLTRE (COMPLEMENTARY FILTER) ---
     // 1. İvmeölçer üzerinden ham açıları trigonometri ile (atan) hesaplıyoruz
     float accRoll = atan(gercek_ay / (sqrt(pow(gercek_ax, 2) + pow(gercek_az, 2))+0.0001)) * 180 / PI;//0 a bölünme hatasını engellemek için +0,0001
     float accPitch = atan(-1 * gercek_ax / (sqrt(pow(gercek_ay, 2) + pow(gercek_az, 2))+0.0001)) * 180 / PI;

     // 2. Jiroskop ve İvmeölçeri ağırlıklı olarak birleştiriyoruz (%96 Gyro, %4 İvme)
     roll = 0.96 * (roll + gercek_gx * dt) + 0.04 * accRoll;
     pitch = 0.96 * (pitch + gercek_gy * dt) + 0.04 * accPitch;

     // 3. YAW HESAPLAMASI (Manyetometre Üzerinden Göreceli)
     float mutlakYaw = atan2(my, mx) * 180 / PI;
     yaw = mutlakYaw - baslangicYaw;
     
     // 4. AÇI NORMALİZASYONU (-180 ile +180 arasına sıkıştırma)
     if (yaw > 180.0) yaw -= 360.0;
     else if (yaw < -180.0) yaw += 360.0;

     // --- YENİ ZAMAN DAMGASI (TIMESTAMP) EKLENTİSİ ---
     // 'suAn' değişkeni paketin hemen başına (MPU'dan sonra) eklendi.
     // String(değişken, 3) komutu virgülden sonra 3 basamak gönderilmesini sağlar
     
     if (suAn - eskiZaman >= 100) {
     eskiZaman = suAn; // Kronometreyi sıfırla
     String mpuVeri = "MPU," + 
     String(suAn) + "," +                 // <-- İŞTE BURASI: Zaman damgası eklendi!
     String(gercek_ax, 3) + "," + 
     String(gercek_ay, 3) + "," + 
     String(gercek_az, 3) + "," + 
     String(gercek_gx, 2) + "," + 
     String(gercek_gy, 2) + "," + 
     String(gercek_gz, 2) + "," + 
     String(sicaklikC, 2) + ","+
     String(roll, 2) + "," + 
     String(pitch, 2) + "," +
     String(yaw, 2) + "," +
     String(mx) + "," + 
     String(my) + "," + 
     String(mz) + "\n"; // Yeni Manyetik veriler eklendi


     Serial.print(mpuVeri); // kalibre edilmiş Veriyi kablosuz olarak fırlatıyorum
     } 
    }
  }
  komutlariKontrolEt();
}

