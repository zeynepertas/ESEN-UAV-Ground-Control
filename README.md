# ESEN UAV Ground Control Station (Yer İstasyonu) 🚀

Bu proje, bir İnsansız Hava Aracı (İHA) için uçtan uca tasarlanmış, endüstri standardı teknolojiler barındıran tam donanımlı bir **Yer Kontrol İstasyonu (GCS)** yazılımıdır. Gömülü sistemlerden başlayıp, mesaj kuyruğu mimarisine ve oradan modern bir web arayüzüne kadar uzanan çift yönlü (bidirectional) veri boru hattını (Data Pipeline) içermektedir.

## 🌟 Proje Özeti
Projenin temel amacı, donanımdan alınan ham sensör verilerinin (İvme, Jiroskop, Pusula, GPS) asenkron mimariler kullanılarak minimum gecikmeyle (low-latency) işlenmesi, arayüzde görselleştirilmesi ve donanıma çift yönlü komut gönderilebilmesidir.

## 🏗️ Kullanılan Teknolojiler ve Mimari

### 1. Donanım ve Gömülü Sistem (C++ / Arduino)
*   **Mikrodenetleyici:** Arduino UNO (ATmega328P) - *UART Serial Haberleşme*
*   **Sensörler:** MPU6050 (6 Eksen IMU), HMC5883L (Pusula/Magnetometer), NEO-6M GPS
*   **Donanım Mimarisi ve Çözümler:** 
    *   **Sensör Füzyonu:** Roll ve Pitch açıları için **Tamamlayıcı Filtre (Complementary Filter)**, Yaw açısı için ise Pusula verisi ile **Relative Zero Calibration** kullanılmıştır.
    *   **I2C Darboğazı Çözümü:** Pusulanın I2C hattını kitlemesini (clock-stretching) önlemek için **Single-Measurement Hack** uygulanarak sensör her 100ms'de bir uyandırılmış ve kilitlenmeler %100 önlenmiştir.
    *   İşlemciyi yormamak için **Data-Ready Hardware Interrupt** kullanılmıştır.

### 2. Haberleşme ve Backend (Python)
*   **Message Broker (RabbitMQ):** Telemetri verileri asenkron ve kayıpsız bir şekilde `pika` kütüphanesi üzerinden RabbitMQ (AMQP) kuyruğuna alınmıştır. 
*   **Çift Yönlü İletişim (Full-Duplex):** Python Bridge yazılımı (`esp_bridge.py`), Serial (UART) üzerinden gelen telemetriyi arayüze aktarırken, arayüzden gelen otonom görev komutlarını (RTL, LAND) anında Arduino'ya gönderir.
*   **REST API:** Sunucu mimarisi **Flask** ile ayağa kaldırılmış ve Angular ile haberleşmesi sağlanmıştır.
*   **Karakutu (Blackbox):** Gelen tüm telemetri paketleri anlık olarak **SQLite** veritabanına kaydedilmektedir.

### 3. Frontend / Arayüz (Angular & TypeScript)
*   **Framework:** Angular (Standalone bileşen mimarisi)
*   **Bileşenler ve UX:**
    *   **RxJS & Memory Management:** RabbitMQ'dan gelen yüksek frekanslı veriler RxJS Observables ile alınmış ve bellek sızıntılarını (memory leak) önlemek için bileşenler kapatıldığında bağlantılar kesilmiştir (OnDestroy).
    *   **Dinamik Grafikler:** Roll, Pitch, Yaw, İvme, Jiroskop ve Manyetik alan verileri CSS/DOM yormayan "Waterfall" kaydırma mantığıyla çizdirilir.
    *   **Harita ve Suni Ufuk:** GPS verileri Leaflet.js haritasında, IMU verileri ise 3 boyutlu CSS animasyonlu Suni Ufuk (Artificial Horizon) göstergesinde canlandırılır.

### 4. Test Otomasyonu (Cypress)
*   Yazılım stabilitesini garanti altına almak için projeye **Cypress Uçtan Uca (E2E) Test Otomasyonu** entegre edilmiştir.
*   Dropdown filtreleme mantıkları, API fetch tetiklemeleri ve UI bileşenlerinin yüklenme testleri sanal bir robot tarafından otomatik koşulmaktadır.

## 🚀 Kurulum ve Çalıştırma

1. **Backend & Broker:** RabbitMQ sunucusunun çalıştığından emin olun ve sırasıyla `esp_bridge.py` ile `app.py` dosyalarını başlatın.
2. **Donanım:** Arduino kodunu cihaza yükleyip USB (COM) üzerinden bağlayın.
3. **Frontend:** `yer-istasyonu` klasörü içinde `npm start` (veya `ng serve`) komutunu çalıştırarak arayüze `http://localhost:4200` adresinden ulaşın.
4. **Test:** `npx cypress open` komutuyla E2E testleri koşturabilirsiniz.
