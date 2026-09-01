import { Injectable } from '@angular/core'; // Angular'da bu sınıfın bir "Servis" (Service) olduğunu belirten dekoratör kütüphanesi.
import { BehaviorSubject, Subject } from 'rxjs'; // Asenkron veri akışını yönetmek için kullanılan ReactiveX (RxJS) kütüphanesi.
import { Client } from '@stomp/stompjs'; // RabbitMQ (veya diğer Message Broker'lar) ile WebSocket üzerinden konuşabilmek için STOMP kütüphanesi.

// @Injectable dekoratörü, bu servisin (TelemetriService) uygulamanın herhangi bir yerinde 
// (Örn: app.ts) kolayca çağrılıp kullanılabileceğini belirtir (Dependency Injection).
// 'providedIn: root' demek, uygulamanın tamamında sadece TANE (Singleton) kopyası olsun demektir.
@Injectable({
  providedIn: 'root'
})
export class TelemetriService {
  
  // --- YAYIN KANALLARI (OBSERVABLES) ---
  // BehaviorSubject: İçerisinde her zaman 'en son' veriyi hafızasında tutan bir yayın kanalıdır.
  // Component (Arayüz) bu kanala abone (subscribe) olduğunda, beklemeden en son veriyi anında alır.
  // Başlangıçta 0'lardan oluşan sahte (dummy) bir veri ile başlatıyoruz.
  private veriKaynagi = new BehaviorSubject<any>({ irtifa: 0, hiz: 0, enlem: 0, boylam: 0 });
  
  // Arayüzün (app.ts) doğrudan 'veriKaynagi'na müdahale edip bozmasını engellemek için,
  // bunu dışarıya sadece "Okunabilir" (Observable) bir kanal (telemetriVerisi$) olarak açıyoruz.
  // Not: Sonundaki dolar ($) işareti, değişkenin bir Observable (Akan Veri) olduğunu gösteren yazılım jargonu/geleneğidir.
  telemetriVerisi$ = this.veriKaynagi.asObservable();

  // Subject: BehaviorSubject'ten farklı olarak geçmişi tutmaz. Sadece "O an bir olay (event) oldu!" demek için kullanılır.
  // Her yeni telemetri geldiğinde, Karakutu tablosuna "Yeni veri geldi, kendini yenile!" diye sinyal (Tetik) çakmak için kullanacağız.
  private karakutuSubject = new Subject<void>();
  karakutuGuncellendi$ = this.karakutuSubject.asObservable();

  // RabbitMQ ile WebSocket bağlantısı kuracak STOMP istemcisi değişkeni.
  private stompClient: Client;

  // Constructor (Yapıcı Metot): Bu servis projede ilk çağrıldığı an (sayfa açıldığında) otomatik çalışır.
  constructor() {
    
    // --- RABBITMQ İLE DOĞRUDAN BAĞLANTI (WEB-STOMP) ---
    // Normalde web tarayıcıları doğrudan RabbitMQ (AMQP) protokolüyle konuşamaz.
    // Bu yüzden RabbitMQ'nun Web-STOMP eklentisini açmıştık. Tarayıcı (Angular) bu eklenti üzerinden
    // WebSockets (ws://) kullanarak 15674 portundan RabbitMQ'ya bağlanır.
    this.stompClient = new Client({
      brokerURL: 'ws://127.0.0.1:15674/ws',
      connectHeaders: {
        login: 'guest',   // RabbitMQ varsayılan kullanıcı adı
        passcode: 'guest',// RabbitMQ varsayılan şifresi
      },
      debug: function (str) {
        // Arka planda STOMP'un gönderip aldığı ham ping-pong (bağlantı testi) mesajlarını konsola yazdır.
        console.log(str);
      },
      reconnectDelay: 5000, // Eğer RabbitMQ kapanırsa veya bağlantı koparsa, 5 saniye bekle ve tekrar bağlanmayı dene.
    });

    // onConnect: STOMP bağlantısı başarıyla kurulduğu (RabbitMQ ile el sıkışıldığı) an tetiklenen fonksiyon.
    this.stompClient.onConnect = (frame) => {
      console.log('[STOMP] RabbitMQ Doğrudan Bağlantısı Başarılı!', frame);
      
      // RabbitMQ'daki 'telemetri_kuyrugu' adlı kuyruğa abone oluyoruz (subscribe).
      // Python'daki 'esp_bridge.py' saniyede bir buraya veri bastıkça, buradaki 'message' değişkenine o veri anında düşer.
      this.stompClient.subscribe('/queue/telemetri_kuyrugu', (message) => {
        // Eğer mesajın bir gövdesi (body) varsa (boş değilse)
        if (message.body) {
            // Gelen veri metin (String) halindeki bir JSON. Bunu JavaScript/TypeScript nesnesine (Object) çeviriyoruz.
            const veri = JSON.parse(message.body);
            
            // Debugging (Hata ayıklama) için gelen veriyi tarayıcının konsoluna (F12) yazdırıyoruz.
            console.log("GELEN CANLI MPU VERİSİ:", veri); 
            
            // BehaviorSubject kanalımıza "Yeni veri var, içindeki eski veriyi bununla değiştir ve abonelere haber ver!" diyoruz. (.next())
            this.veriKaynagi.next(veri);
            
            // Karakutu kanalına "Boş bir sinyal (tetik)" çakıyoruz. Karakutu bunu duyunca API'den geçmiş verileri tekrar çekecek.
            this.karakutuSubject.next();
        }
      });
    };

    // onStompError: Eğer şifre yanlışsa veya RabbitMQ çökerse buraya düşer.
    this.stompClient.onStompError = (frame) => {
      console.error('[STOMP] Hata: ', frame.headers['message']);
    };

    // Bütün ayarları (onConnect vs.) yaptıktan sonra, bağlantı motorunu fiilen çalıştır (Start/Activate).
    this.stompClient.activate();
  }

  // --- ARAYÜZDEN KOMUT GÖNDERME FONKSİYONU ---
  // Arayüzdeki (HTML) butonlara (RTL, LAND vb.) tıklandığında çalışan asenkron (async) fonksiyon.
  async komutGonder(komutTipi: string) {
    console.log(`[Komut] ${komutTipi} gönderiliyor...`);
    try {
      // Komutu RabbitMQ'ya Web-STOMP ile de atabilirdik ama güvenlik ve Loglama için
      // komutları Python Flask API'mize (app.py) HTTP POST isteği olarak atıyoruz.
      // Flask bunu alıp loglayıp RabbitMQ'ya kendi iletecektir.
      await fetch('http://127.0.0.1:5000/api/komut', {
        method: 'POST', // Sunucuya yeni bir veri gönderdiğimiz için POST methodu kullanıyoruz.
        headers: {
          'Content-Type': 'application/json' // Sunucuya "Sana metin gönderiyorum ama bu bir JSON" diyoruz.
        },
        body: JSON.stringify({ komut: komutTipi }) // "{ 'komut': 'RTL' }" objesini metne çevirip yolluyoruz.
      });
    } catch (err) {
      // Eğer Flask sunucusu (app.py) kapalıysa fetch hata (Exception) verir, burada o hatayı yakalıyoruz.
      console.error('Komut gönderme hatası:', err);
    }
  }
}