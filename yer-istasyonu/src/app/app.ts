import { Component, signal, computed, inject, DestroyRef, AfterViewInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop'; // Component silindiğinde arka planda çalışan dinlemeleri (memory leak'i) durdurmak için
import { RouterOutlet } from '@angular/router'; // Birden fazla sayfa (Routing) yapısı kullanmak istersek diye ekli
import * as L from 'leaflet'; // Google Maps benzeri, açık kaynaklı harita kütüphanesi (Leaflet)
// Kendi yazdığımız Telemetri Servisini içeri aktarıyoruz. (Bu servis RabbitMQ ile konuşmayı hallediyor)
import { TelemetriService } from './telemetri';
import { NgIf } from '@angular/common';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);


// @Component: Bu sınıfın (class) bir Angular Bileşeni (Component) olduğunu belirten dekoratör.
@Component({
  selector: 'app-root', // Bu bileşenin HTML etiket adı (Örn: index.html içinde <app-root></app-root> olarak çağrılır)
  imports: [RouterOutlet, NgIf], 
  templateUrl: './app.html', // Bu bileşenin görsel (HTML) yüzü
  styleUrl: './app.css'      // Bu bileşenin stil (CSS) dosyası
})
export class App implements AfterViewInit {
  angleChart: any;
  accelChart: any;
  gyroChart: any;

  ngAfterViewInit_silindi() {
    // I am completely deleting this chunk to fix duplicate function, leaving this blank line.
  }

  grafikleriBaslat() {
    // 1. Açı Grafiği
    this.angleChart = new Chart('angleChart', {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Roll', data: [], borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Pitch', data: [], borderColor: '#4ade80', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Yaw', data: [], borderColor: '#fbbf24', borderWidth: 1.5, pointRadius: 0 }
        ]
      },
      options: { responsive: true, animation: false, scales: { x: { display: false } } }
    });

    // 2. İvme Grafiği
    this.accelChart = new Chart('accelChart', {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Ax', data: [], borderColor: '#f43f5e', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Ay', data: [], borderColor: '#a855f7', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Az', data: [], borderColor: '#06b6d4', borderWidth: 1.5, pointRadius: 0 }
        ]
      },
      options: { responsive: true, animation: false, scales: { x: { display: false } } }
    });

    // 3. Jiroskop Grafiği
    this.gyroChart = new Chart('gyroChart', {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Gx', data: [], borderColor: '#ec4899', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Gy', data: [], borderColor: '#84cc16', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Gz', data: [], borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0 }
        ]
      },
      options: { responsive: true, animation: false, scales: { x: { display: false } } }
    });
  }

  // Canlı veriler her geldiğinde (WebSocket / SSE döngüsünde) bu fonksiyonu çağıracağız:
  grafikleriGuncelle(veri: any) {
    const zamanDamgasi = new Date().toLocaleTimeString();

    // Maksimum 20 veri tutarak ekranın kaymasını sağlıyoruz
    const maxVeri = 20;

    [this.angleChart, this.accelChart, this.gyroChart].forEach(chart => {
      if (chart.data.labels.length > maxVeri) {
        chart.data.labels.shift();
        chart.data.datasets.forEach((ds: any) => ds.data.shift());
      }
    });

    // Açı verileri
    this.angleChart.data.labels.push(zamanDamgasi);
    this.angleChart.data.datasets[0].data.push(veri.roll);
    this.angleChart.data.datasets[1].data.push(veri.pitch);
    this.angleChart.data.datasets[2].data.push(veri.yaw);
    this.angleChart.update('none');

    // İvme verileri
    this.accelChart.data.labels.push(zamanDamgasi);
    this.accelChart.data.datasets[0].data.push(veri.ax);
    this.accelChart.data.datasets[1].data.push(veri.ay);
    this.accelChart.data.datasets[2].data.push(veri.az);
    this.accelChart.update('none');

    // Jiroskop verileri
    this.gyroChart.data.labels.push(zamanDamgasi);
    this.gyroChart.data.datasets[0].data.push(veri.gx);
    this.gyroChart.data.datasets[1].data.push(veri.gy);
    this.gyroChart.data.datasets[2].data.push(veri.gz);
    this.gyroChart.update('none');
  }

  // --- SERVİSLERİN İÇE AKTARILMASI (DEPENDENCY INJECTION) ---
  // inject(): Angular 16+ ile gelen yeni ve temiz bir servis çağırma yöntemidir. (Eski versiyonlarda constructor içinde yapılırdı).
  
  // RabbitMQ (STOMP) bağlantısını, veri akışını ve komut gönderimini yöneten "TelemetriService" servisini alıyoruz.
  private telemetriServisi = inject(TelemetriService);
  
  // DestroyRef: Bu bileşen ekrandan kaybolduğunda (Örn: Başka sayfaya geçildiğinde) 
  // arka planda dönen sonsuz dinlemeleri öldürmek için gereken bir referans.
  private destroyRef = inject(DestroyRef);

  // --- ANGULAR SİNYALLERİ (SIGNALS) - ANLIK DURUM YÖNETİMİ ---
  // signal(): Angular 16+ ile gelen devrimsel bir özelliktir. 
  // İçindeki veri her değiştiğinde, HTML dosyasında bu veriyi kullanan yerleri saniyesinde günceller (Reactivity).
  irtifa = signal(0);
  hiz = signal(0);
  enlem = signal<number>(0);
  boylam = signal<number>(0);
  durum = signal<string>('NORMAL');
  zeminYuksekligi = signal<number>(885); // ODTÜ/Bilkent bölgesinin deniz seviyesinden tahmini yüksekliği
  sicaklik = signal(0);
  ax = signal(0);
  ay = signal(0);
  az = signal(0);
  gx = signal(0);
  gy = signal(0);
  gz = signal(0);
  roll = signal(0);  // Ufuk Göstergesi için Yatış açısı
  pitch = signal(0); // Ufuk Göstergesi için Yunuslama açısı
  yaw = signal(0);   // Yönelme açısı
  zamanDamgasi = signal<number>(0); // ESP32'nin veri üretim zamanı

  // --- BAĞLANTI KOPMASI (WATCHDOG) DEĞİŞKENLERİ ---
  baglantiKoptu = signal<boolean>(false); // Uyarıyı tetikleyecek sinyal
  private sonVeriZamani: number = Date.now(); // Son verinin geldiği milisaniye
  private watchdogTimer: any; // Sayacın kendisi

  // --- HARİTA DEĞİŞKENLERİ ---
  private map: L.Map | undefined;       // Haritanın ta kendisi (Objesi)
  private marker: L.Marker | undefined; // Haritadaki Dronun konumu gösteren raptiye (pin)

  // Sınır ihlali durumu için hazırladığımız özel KIRMIZI uyarı ikonu objesi
  private warningIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41], // İkonun genişlik ve yüksekliği (piksel)
    iconAnchor: [12, 41], // İkonun haritadaki koordinata tam olarak neresinden batacağı (Alt orta noktası)
    popupAnchor: [1, -34], // Uyarı balonu (Popup) çıkarsa ikonun neresinde çıksın
    shadowSize: [41, 41]
  });
  
  // Her şey yolundaysa kullanılacak NORMAL (Mavi) ikon objesi
  private normalIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
  });

  // --- HESAPLANMIŞ SİNYALLER (COMPUTED SIGNALS) ---
  // computed(): Başka sinyallerin (Örn: enlem, boylam) değerlerini dinleyip, anlık bir formül çıkarır.
  // Enlem ve Boylam değiştiği an bu formül otomatik olarak tekrar hesaplanır.
  
  // Eğer enlem veya boylam 0 ise, "GPS Koptu" değişkenini True yapar. Arayüzde alarm çıkar.
  gpsKoptu = computed(() => this.enlem() === 0 || this.boylam() === 0);
  
  // Sınır İhlali Formülü (Geofencing): Dron sanal bir kafesin (belirli koordinatların) dışına çıktıysa True döner.
  sinirIhlali = computed(() => {//(Computed): Başka sinyallere bakarak otomatik karar veren otonom zekalardır.
       const lat = this.enlem();
       const lon = this.boylam();
       if (lat === 0 || lon === 0) return false;
       // 39.88 ile 39.91 arası (Enlem) ve 32.76 ile 32.79 arası (Boylam) bizim güvenli ODTÜ/Bilkent uçuş sahamızdır.
       return lat < 39.8800 || lat > 39.9100 || lon < 32.7600 || lon > 32.7900;  
  });

  // Çarpma Riski (Yer Yakınlık Uyarısı - GPWS): Dron yere çok yakınsa veya "Araziden Kaçınma" modundaysa True döner.
  carpmaRiski = computed(() => {
    // Eğer irtifa(Deniz Seviyesi), zemin_rakimi + 40 metrenin altına düştüyse dron çok alçalmıştır uyarısı ver!
    return this.durum() === 'TERRAIN_AVOIDANCE' || (this.irtifa() > 0 && this.irtifa() < this.zeminYuksekligi() + 40);
  });

  // --- CONSTRUCTOR (BİLEŞENİN KALBİ) ---
  // Bu sınıf ekranda ilk oluşturulduğu (sayfa yüklendiği) an sadece 1 kere çalışır.
  constructor() {
    // 1. CANLI TELEMETRİ ABONELİĞİ (Saniyede 1 kez çalışır)
    // Telemetri servisindeki "telemetriVerisi$" yayın kanalına (Observable) abone (subscribe) oluyoruz.
    this.telemetriServisi.telemetriVerisi$
      // takeUntilDestroyed: Bu sayfa kapatılırsa (örn. başka menüye geçilirse) arkada boş yere dinleme yapmaya devam edip 
      // rami şişirmesin diye, bu dinlemeyi de otomatik olarak parçala/sil diyoruz.
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((veri) => {
        console.log("RabbitMQ'dan paket geldi:", veri);
        // Veri geldiği an sayacı sıfırla ve alarmı kapat!
        this.sonVeriZamani = Date.now();
        this.baglantiKoptu.set(false);

        // RabbitMQ'dan bize ulaşan yeni veri sözlüğünü aldık ve Angular Sinyallerimizi (.set ile) güncelledik.
        // Bu sinyaller güncellendiği an HTML tarafındaki (Örn: {{ roll() }}) kısımlar anında otomatik değişecek!
        this.irtifa.set(veri.irtifa);
        this.hiz.set(veri.hiz);
        this.enlem.set(veri.enlem);
        this.boylam.set(veri.boylam);
        
        // Eğer paket içinde bu veriler varsa güncelle (Bazen paket eksik gelebilir, çökmesin diye if koyuyoruz)
        if (veri.sicaklik !== undefined) this.sicaklik.set(veri.sicaklik);
        if (veri.ax !== undefined) this.ax.set(veri.ax);
        if (veri.ay !== undefined) this.ay.set(veri.ay);
        if (veri.az !== undefined) this.az.set(veri.az);
        if (veri.gx !== undefined) this.gx.set(veri.gx);
        if (veri.gy !== undefined) this.gy.set(veri.gy);
        if (veri.gz !== undefined) this.gz.set(veri.gz);
        if (veri.roll !== undefined) this.roll.set(veri.roll);
        if (veri.pitch !== undefined) this.pitch.set(veri.pitch);
        if (veri.yaw !== undefined) this.yaw.set(veri.yaw);
        if (veri.zaman_damgasi !== undefined) {
          this.zamanDamgasi.set(veri.zaman_damgasi);
        }
        if (veri.zemin_rakimi !== undefined) {
          this.zeminYuksekligi.set(veri.zemin_rakimi);
        }
        if (veri.durum) {
          this.durum.set(veri.durum);
        }

        // --- HARİTANIN GÜNCELLENMESİ ---
        // Eğer koordinatlar geçerliyse (undefined değilse), haritadaki raptiyenin yerini değiştir.
        if (veri.enlem !== undefined && veri.boylam !== undefined) {
          this.enlem.set(veri.enlem);
          this.boylam.set(veri.boylam);
          // Harita fonksiyonuna yolla
          this.updateMapPosition(veri.enlem, veri.boylam);
        }

        // --- GRAFİKLERİN GÜNCELLENMESİ ---
        this.grafikleriGuncelle(veri);
      });
      
    // 2. KARAKUTU ABONELİĞİ (SADECE veritabanında yeni bir kayıt olduğunda çalışır)
    // Normalde telemetri saniyede onlarca kez gelir ama Karakutu servisi sadece veritabanında değişiklik olduğunda bir "Tetik (next)" yollar.
    this.telemetriServisi.karakutuGuncellendi$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        // Tetik geldiği an, veritabanından en son satırları çekmek için gecmisiGetir() fonksiyonunu çağırıyoruz.
        // Bu sayede alttaki dev tablo anlık olarak büyümeye başlar.
        this.gecmisiGetir();
      });


      // --- BEKÇİ KÖPEĞİ (WATCHDOG) BAŞLATMA ---
     // Her 1 saniyede (1000 ms) bir uyanıp süreyi kontrol eder.
     this.watchdogTimer = setInterval(() => {
      const gecenSure = Date.now() - this.sonVeriZamani;
      console.log("Timer çalışıyor. Geçen süre (ms):", gecenSure);
      // Eğer son verinin üzerinden 3 saniyeden (3000 ms) fazla zaman geçtiyse
      if (gecenSure > 3000) {
        this.baglantiKoptu.set(true); // Alarmı tetikle!
        console.log("SİSTEM UYARISI: Bağlantı koptu, sayaç 3 saniyeyi geçti!"); // <-- Test için ekledik
      }
     }, 1000);

     // Bileşen (sayfa) kapatılırsa timer'ı temizle ki arka planda sonsuza dek çalışıp RAM'i şişirmesin (Memory Leak önlemi).
     this.destroyRef.onDestroy(() => clearInterval(this.watchdogTimer));

  }


  // --- HARİTANIN YÜKLENMESİ ---
  // ngAfterViewInit(): Angular'ın "HTML yüklendi, ekran çizildi" deme noktasıdır. 
  // Haritayı bu noktadan önce çizersek, HTML div'i henüz var olmadığı için hata verir!
  ngAfterViewInit(): void {
    // Leaflet (L) kütüphanesini kullanarak 'map' id'li HTML div'ine bir harita göm. 
    // Merkezi 39.8950, 32.7750 (Ankara/ODTÜ civarı) yap ve yakınlaştırma (Zoom) oranını 14 olarak ayarla.
    this.map = L.map('map').setView([39.8950, 32.7750], 14);

    // Haritanın arka plan resimlerini (TileLayer) OpenStreetMap üzerinden çek (Bedava olduğu için).
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(this.map);

    // Dronun ilk duracağı noktaya Mavi ikonu koyarak bir raptiye (Marker) oluştur ve haritaya ekle.
    this.marker = L.marker([39.8950, 32.7750], { icon: this.normalIcon }).addTo(this.map);
    
    // Haritada sınır ihlalini görsel olarak anlamak için yeşil bir dikdörtgen (Sanal Kafes - Geofence) çiz.
    const safeBounds: L.LatLngBoundsExpression = [
      [39.8800, 32.7600], // Dikdörtgenin Güney Batı (Alt Sol) köşesi
      [39.9100, 32.7900]  // Dikdörtgenin Kuzey Doğu (Üst Sağ) köşesi
    ];
    // Bunu haritaya %10 (0.1) saydamlıkla yeşil renkte çiz.
    L.rectangle(safeBounds, { color: '#28a745', weight: 2, fillOpacity: 0.1 }).addTo(this.map);

    // --- GRAFİKLERİN YÜKLENMESİ ---
    this.grafikleriBaslat();
  }

  // --- DRONUN HARİTADA HAREKET ETMESİ ---
  // Bu fonksiyon her yeni GPS verisi geldiğinde çağrılır.
  private updateMapPosition(lat: number, lon: number) {
    if (this.marker && this.map) {
      // Gelen sayıları Leaflet Koordinat Objesine çevir
      const newLatLng = new L.LatLng(lat, lon);
      
      // Raptiyenin yerini (SetLatLng) yeni objeye (koordinata) doğru kaydır. 
      this.marker.setLatLng(newLatLng);
      
      // Eğer computed sinyalimiz olan sinirIhlali() True dönmüşse:
      if (this.sinirIhlali()) {
        // İkonun rengini kırmızıya (Uyarı) çevir
        this.marker.setIcon(this.warningIcon);
        // İkonun tepesinde bir bilgi balonu aç (Popup)
        this.marker.bindPopup('<b>UYARI:</b> Güvenli Bölge Dışında!').openPopup();
      } else {
        // Sınırın içindeyse her şey yolunda, tekrar mavi ikona geç ve uyarı balonunu kapat.
        this.marker.setIcon(this.normalIcon);
        this.marker.closePopup();
      }
    }
  }

  // --- KARAKUTU DEĞİŞKENLERİ VE FONKSİYONLARI ---
  gecmisVeriler = signal<any[]>([]); // Veritabanından gelen satırların (dizilerin) tutulduğu sinyal listesi.
  kayitLimiti = signal<number>(20);  // Tabloda varsayılan olarak kaç satır gösterileceğini tutan sinyal.
  seciliFiltre = signal<string>('tumu');

  // "Daha Fazla Yükle" butonuna tıklandığında çalışır.
  dahaFazlaYukle() {
    // Limiti 20 daha artır (20 -> 40 -> 60 ...)
    this.kayitLimiti.update(limit => limit + 20);
    // Veritabanını tekrar çağır ki yeni limite göre (Örn: 40 satır) veriyi getirsin.
    this.gecmisiGetir();
  }



  // API'den (app.py) geçmiş verileri çeken asenkron (async) fonksiyon.api üzerinden python(flask) ile konuştuğumuz bölüm
  async gecmisiGetir() {
    try {
      // Python Flask sunucumuzdaki /api/gecmis linkine istek atıyoruz. Limit değişkenini de URL sonuna ekliyoruz.
      const response = await fetch(`http://127.0.0.1:5000/api/gecmis?limit=${this.kayitLimiti()}&filtre=${this.seciliFiltre()}`);
      // Dönen JSON metnini JavaScript listesine çevir.
      const data = await response.json();
      // Tablomuzu besleyen 'gecmisVeriler' sinyaline bu listeyi yükle. (Bunu yapınca tablo anında güncellenir).
      this.gecmisVeriler.set(data);
    } catch (error) {
      console.error("Geçmiş veriler alınamadı:", error);
    }
  }
 

    // Arayüzdeki menü (Dropdown) değiştiğinde tetiklenecek fonksiyon
  filtreDegistir(event: Event) {
    const secilenDeger = (event.target as HTMLSelectElement).value;
    this.seciliFiltre.set(secilenDeger); // Yeni seçimi kaydet
    this.gecmisiGetir(); // Tabloyu yeni filtreyle baştan çek
  }

csvIndir() {
    // Tarayıcının yeni bir sekmede doğrudan endpoint'i tetikleyip dosyayı indirmesini sağlar
    const link = document.createElement('a');
    link.href = 'http://127.0.0.1:5000/api/export/csv';
    link.target = '_blank';
    link.click();
  }

  // --- KOMUT GÖNDERME FONKSİYONLARI ---
  // Bu fonksiyonlar Arayüzdeki (HTML) tuşlara tıklandığında (Örn: (click)="eveDon()") çalışır.
  
  eveDon() {
    // Telemetri servisindeki komutGonder fonksiyonunu çağır ve ona "RTL" metnini ver.
    this.telemetriServisi.komutGonder('RTL'); // Return To Launch
  }

  acilDurdur() {
    this.telemetriServisi.komutGonder('EMERGENCY_STOP'); 
  }
  
  guvenliInis() {
    this.telemetriServisi.komutGonder('LAND');
  }

  havalan() {
    this.telemetriServisi.komutGonder('TAKEOFF');
  }
  
  // Joystick Yön Komutları
  gitKuzey() { this.telemetriServisi.komutGonder('NORTH'); }
  gitGuney() { this.telemetriServisi.komutGonder('SOUTH'); }
  gitDogu() { this.telemetriServisi.komutGonder('EAST'); }
  gitBati() { this.telemetriServisi.komutGonder('WEST'); }
}