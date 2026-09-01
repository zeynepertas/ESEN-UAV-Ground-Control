# ESEN UAV Ground Control Station (Yer İstasyonu) 🚀

Bu proje, bir İnsansız Hava Aracı (İHA) için uçtan uca tasarlanmış, endüstri standardı teknolojiler barındıran tam donanımlı bir **Yer Kontrol İstasyonu (GCS)** yazılımıdır. Gömülü sistemlerden başlayıp, mesaj kuyruğu mimarisine ve oradan modern bir web arayüzüne kadar uzanan veri boru hattını (Data Pipeline) içermektedir.

## 🌟 Proje Özeti
Projenin temel amacı, donanımdan alınan ham sensör verilerinin (İvme, Jiroskop, GPS, Sıcaklık) asenkron mimariler kullanılarak minimum gecikmeyle (low-latency) işlenmesi, arayüzde görselleştirilmesi ve uçuş güvenliği algoritmalarıyla denetlenmesidir.

## 🏗️ Kullanılan Teknolojiler ve Mimari

### 1. Donanım ve Gömülü Sistem (C++ / ESP32)
*   **Mikrodenetleyici:** ESP32 (Wi-Fi TCP Socket Haberleşmesi)
*   **Sensörler:** MPU6050 (6 Eksen IMU), NEO-6M GPS
*   **Donanım Mimarisi:** 
    *   İşlemciyi yormamak için **Data-Ready Hardware Interrupt** kullanılmıştır.
    *   Jiroskop sapmasını (drift) önlemek için özel **Ölü Bant (Deadband) Filtresi** kodlanmıştır.
    *   Roll ve Pitch açıları için **Tamamlayıcı Filtre (Complementary Filter)** ile sensör füzyonu gerçekleştirilmiştir.
    *   Ağ gecikmelerini önlemek için bağlantı koptuğunda kilitlenmeyi engelleyen Failsafe mekanizmaları (Timeout) kullanılmıştır.

### 2. Haberleşme ve Backend (Python)
*   **Message Broker:** **RabbitMQ** kullanılarak telemetri verileri asenkron ve kayıpsız bir şekilde Pika kütüphanesi üzerinden kuyruğa (Queue) alınmıştır. PXI kartlarından veri okuma mantığına (Python Wrapper) benzer bir Soket köprüsü (Bridge) kurulmuştur.
*   **REST API:** Sunucu mimarisi **Flask** ile ayağa kaldırılmış ve Angular ile REST prensipleri üzerinden haberleşmesi sağlanmıştır.
*   **Karakutu (Blackbox):** Gelen tüm telemetri paketleri anlık olarak **SQLite** veritabanına kaydedilmektedir.

### 3. Frontend / Arayüz (Angular & TypeScript)
*   **Framework:** Angular (Standalone bileşen mimarisi)
*   **Tasarım:** Siberpunk / Glassmorphism temalı, tamamen Responsive (Mobil ve Web uyumlu) arayüz.
*   **Bileşenler:**
    *   **RxJS & Signals:** RabbitMQ'dan gelen yüksek frekanslı veriler Angular Signals ile ekranda anında güncellenir.
    *   **Chart.js:** Anlık uçuş açıları, ivme ve jiroskop verileri 3 farklı dinamik grafikte çizdirilir.
    *   **Leaflet.js:** GPS verileri gerçek zamanlı olarak harita üzerinde işaretlenir ve yeşil renkte bir **Sanal Sınır (Geofence)** çizilerek ihlal durumunda alarm tetiklenir.
    *   **Suni Ufuk (HUD):** Dronun Roll ve Pitch açılarına göre 3 boyutlu tepki veren Artificial Horizon aracı CSS animasyonlarıyla kodlanmıştır.

### 4. Test Otomasyonu (Cypress)
*   Yazılım uçuş güvenliğini garanti altına almak için projeye **Cypress Uçtan Uca (E2E) Test Otomasyonu** entegre edilmiştir.
*   `yer-istasyonu.cy.ts` dosyası içerisinde sistemin başarılı yüklendiği, Karakutu tablosunun geldiği ve "Acil Motor Durdurma", "Eve Dönüş (RTL)" gibi otonom butonların tıklanabilirlikleri sanal bir robot tarafından saniyeler içinde otomatik olarak test edilmektedir.

## 🚀 Kurulum ve Çalıştırma

1. **Backend & Broker:** RabbitMQ sunucusunun çalıştığından emin olun ve sırasıyla `esp_bridge.py` ile `app.py` dosyalarını başlatın.
2. **Donanım:** ESP32 kodunu cihaza yükleyip güç verin.
3. **Frontend:** `yer-istasyonu` klasörü içinde `npm start` (veya `ng serve`) komutunu çalıştırarak arayüze `localhost:4200` adresinden ulaşın.
4. **Test:** `npx cypress open` komutuyla E2E testleri koşturabilirsiniz.
