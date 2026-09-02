from flask import Flask, jsonify, request # Flask: Python tabanlı hafif bir web sunucu altyapısı (Backend API kurmak için). jsonify: Verileri JSON formatına dönüştürür. request: Gelen HTTP isteklerindeki verileri okur.
from flask_cors import CORS # CORS (Cross-Origin Resource Sharing): Arayüzün (Angular, localhost:4200) farklı bir porttan (Flask, localhost:5000) veri çekerken tarayıcı engeline (CORS hatası) takılmasını önler.
import pika # RabbitMQ (Mesaj Kuyruğu) ile iletişim kurmamızı sağlayan Python kütüphanesi.
import json # Verileri metin tabanlı (JSON) olarak paketlemek ve çözmek (parse etmek) için kullanılır.
import threading # Aynı anda hem web sunucusunu (Flask) çalıştırıp hem de arka planda RabbitMQ dinleyebilmek için İş Parçacığı (Thread) kullanıyoruz.
import sqlite3 # Hafif ve dosya tabanlı bir SQL veritabanı motoru. Ayrı bir sunucu kurulumu gerektirmez.
from datetime import datetime # Veritabanına kayıt atarken o anın tarih ve saat (Timestamp) bilgisini almak için.
from config import RABBITMQ_URL # Şifreleri ve gizli sunucu adreslerini ana kodda açık etmemek için dışarıdaki 'config.py' dosyasından içe aktarıyoruz.
import csv
from io import StringIO
from flask import Response



# Flask uygulamasını başlat. '__name__' parametresi, uygulamanın ana modülden çalıştığını belirtir.
app = Flask(__name__)
# Tüm API uçlarına (routes) diğer domain/portlardan erişime izin ver (Angular'ın veri çekebilmesi için şart).
CORS(app)

# RabbitMQ'dan saniyede bir yağan güncel telemetri verilerini geçici olarak tutacağımız hafıza (RAM) sözlüğü.
anlik_veri = {"irtifa": 0, "hiz": 0}

# Veritabanına gereksiz yere aynı saniyede aynı verileri tekrar tekrar kaydedip diski doldurmamak (Spam önlemek) için
# en son kaydettiğimiz paketin içeriğini (özetini) tuttuğumuz değişken.
son_kaydedilen_veri = None

def veritabani_hazirla():
    """
    Sistem ilk çalıştığında 'ucus_verileri.db' adında bir SQLite veritabanı dosyası oluşturur.
    İçerisinde İHA'nın tüm sensör verilerini (Karakutu) tutacak 'telemetri' tablosunu hazırlar.
    """
    # 'ucus_verileri.db' dosyasına bağlan. Dosya yoksa sıfırdan oluşturur.
    conn = sqlite3.connect('ucus_verileri.db', timeout=10)
    # Veritabanında SQL komutları (sorguları) çalıştırabilmek için bir imleç (cursor) açıyoruz.
    cursor = conn.cursor()
    
    # Eğer 'telemetri' adında bir tablo yoksa (IF NOT EXISTS), şu sütunlarla oluştur:
    # id: Otomatik artan (AUTOINCREMENT) eşsiz kayıt numarası (Birincil Anahtar).
    # zaman: Metin formatında (TEXT) kayıt tarihi ve saati.
    # irtifa, hiz, enlem, boylam vb. : Kesirli (virgüllü) sayı tipinde (REAL) sensör verileri.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetri (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zaman TEXT,
            irtifa REAL,
            hiz REAL,
            enlem REAL,
            boylam REAL,
            durum TEXT,
            sicaklik REAL,
            ax REAL,
            ay REAL,
            az REAL,
            gx REAL,
            gy REAL,
            gz REAL,
            roll REAL,
            pitch REAL
        )
    ''')
    # Yaptığımız değişiklikleri (Tablo oluşturmayı) veritabanına kalıcı olarak kaydet (İşlemi onayla).
    conn.commit()
    # İşimiz bittiğinde bağlantıyı kapat ki dosya kitlenmesin (Memory Leak olmasın).
    conn.close()

# Program başlarken veritabanının ve tablonun var olduğundan emin olmak için hemen çalıştır.
veritabani_hazirla()

# --- GERİYE DÖNÜK UYUMLULUK (MIGRATION) BLOKLARI ---
# Eğer programı ilk yazdığımızda tabloda 'durum' veya 'sicaklik' sütunları yoktuysa,
# sonradan eklediğimizde kodun patlamaması için (Eski tabloya yeni sütun eklemek için) ALTER TABLE kullanıyoruz.
# try-except bloğu kullanıyoruz çünkü sütun zaten varsa ALTER komutu hata verir. Hata verirse (except), boş ver (pass) deyip geçiyoruz.
try:
    conn = sqlite3.connect('ucus_verileri.db', timeout=10)
    conn.execute("ALTER TABLE telemetri ADD COLUMN durum TEXT")
    conn.commit()
    conn.close()
except:
    pass

try:
    conn = sqlite3.connect('ucus_verileri.db', timeout=10)
    conn.execute("ALTER TABLE telemetri ADD COLUMN sicaklik REAL")
    conn.execute("ALTER TABLE telemetri ADD COLUMN ax REAL")
    conn.execute("ALTER TABLE telemetri ADD COLUMN ay REAL")
    conn.execute("ALTER TABLE telemetri ADD COLUMN az REAL")
    conn.commit()
    conn.close()
except:
    pass

try:
    conn = sqlite3.connect('ucus_verileri.db', timeout=10)
    conn.execute("ALTER TABLE telemetri ADD COLUMN gx REAL")
    conn.execute("ALTER TABLE telemetri ADD COLUMN gy REAL")
    conn.execute("ALTER TABLE telemetri ADD COLUMN gz REAL")
    conn.commit()
    conn.close()
except:
    pass

try:
    conn = sqlite3.connect('ucus_verileri.db', timeout=10)
    # İHA'nın Yatış (Roll) ve Yunuslama (Pitch) açılarını barındıracak en son eklediğimiz sütunlar.
    conn.execute("ALTER TABLE telemetri ADD COLUMN roll REAL")
    conn.execute("ALTER TABLE telemetri ADD COLUMN pitch REAL")
    conn.commit()
    conn.close()
except:
    pass

def rabbitmq_dinle():
    """
    Arka planda (Thread içinde) sonsuz döngüde çalışarak RabbitMQ'daki 'telemetri_kuyrugu'nu dinler.
    Gelen yeni sensör verilerini alır ve değişmişse 'ucus_verileri.db' veritabanına yazar (Karakutu Kaydı).
    Aynı zamanda dronun koordinatlarına bakarak Sınır İhlali (Geofencing) denetimi yapar.
    """
    global anlik_veri, son_kaydedilen_veri
    
    # RabbitMQ'ya bağlan
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    
    # Dinleyeceğimiz telemetri kuyruğunu oluştur/doğrula.
    channel.queue_declare(queue='telemetri_kuyrugu', durable=True)
    # Acil bir durumda uyarı fırlatabilmek için 'acil_durum' kuyruğunu da tanımla.
    channel.queue_declare(queue='acil_durum', durable=True)

    def callback(ch, method, properties, body):
        # RabbitMQ'ya mesaj (Telemetri) geldiğinde bu alt fonksiyon tetiklenir.
        global anlik_veri, son_kaydedilen_veri
        try:
            # Gelen byte formatındaki mesajı (JSON metnini) Python sözlüğüne çevir.
            veri = json.loads(body)
            
            # Gelen sözlüğün (veri) içindeki değerleri, bizim 'anlik_veri' havuzumuza kopyala.
            # .get("irtifa", varsayılan_değer) kullanımı: Eğer gelen pakette "irtifa" yoksa, kodu çökertme, eski değeri koru demektir.
            anlik_veri["irtifa"] = veri.get("irtifa", anlik_veri.get("irtifa", 0))
            anlik_veri["hiz"] = veri.get("hiz", anlik_veri.get("hiz", 0))
            anlik_veri["enlem"] = veri.get("enlem", 0)
            anlik_veri["boylam"] = veri.get("boylam", 0)
            anlik_veri["durum"] = veri.get("durum", "NORMAL")
            anlik_veri["sicaklik"] = veri.get("sicaklik", 0)
            anlik_veri["ax"] = veri.get("ax", 0)
            anlik_veri["ay"] = veri.get("ay", 0)
            anlik_veri["az"] = veri.get("az", 0)
            anlik_veri["gx"] = veri.get("gx", 0)
            anlik_veri["gy"] = veri.get("gy", 0)
            anlik_veri["gz"] = veri.get("gz", 0)
            anlik_veri["roll"] = veri.get("roll", 0)
            anlik_veri["pitch"] = veri.get("pitch", 0)
            anlik_veri["yaw"] = veri.get("yaw", 0)

            # --- VERİTABANINA AKILLI KAYIT SİSTEMİ ---
            # MPU verileri aşırı hızlı akar, saniyede onlarca kez aynı koordinat ve açı gelebilir.
            # Diskin şişmesini engellemek için, o anki tüm verilerin bir 'Özetini' (Tuple - Demet formunda) çıkarıyoruz.
            mevcut_ozet = (
                anlik_veri["durum"], 
                anlik_veri["irtifa"], 
                anlik_veri["hiz"], 
                anlik_veri["enlem"], 
                anlik_veri["boylam"],
                anlik_veri["sicaklik"],
                anlik_veri["ax"],
                anlik_veri["ay"],
                anlik_veri["az"],
                anlik_veri["gx"],
                anlik_veri["gy"],
                anlik_veri["gz"],
                anlik_veri["roll"],
                anlik_veri["pitch"],
                anlik_veri["yaw"]
            )
            
            # Eğer şu anki değerler özeti, veritabanına en son kaydettiğimiz özetten FARKLIYSA
            # (Yani dronun açısı, konumu veya durumu zerrece değiştiyse) o zaman veritabanına yeni satır ekle.
            if son_kaydedilen_veri != mevcut_ozet:
                conn = sqlite3.connect('ucus_verileri.db', timeout=10)
                cursor = conn.cursor()
                
                # O anki bilgisayar saatini 'Yıl-Ay-Gün Saat:Dakika:Saniye' formatında metne çevir.
                su_an = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # INSERT INTO ile SQL Tablosuna yeni bir satır (Karakutu kaydı) ekle.
                # '?' işaretleri SQL Injection saldırılarını önlemek için güvenli parametre atama yöntemidir.
                cursor.execute('''
                    INSERT INTO telemetri (zaman, irtifa, hiz, enlem, boylam, durum, sicaklik, ax, ay, az, gx, gy, gz, roll, pitch, yaw)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    su_an, 
                    anlik_veri["irtifa"], 
                    anlik_veri["hiz"], 
                    anlik_veri["enlem"], 
                    anlik_veri["boylam"], 
                    anlik_veri["durum"],
                    anlik_veri["sicaklik"],
                    anlik_veri["ax"],
                    anlik_veri["ay"],
                    anlik_veri["az"],
                    anlik_veri["gx"],
                    anlik_veri["gy"],
                    anlik_veri["gz"],
                    anlik_veri["roll"],
                    anlik_veri["pitch"],
                    anlik_veri["yaw"]
                ))
                conn.commit() # Kaydı onayla
                conn.close()  # Veritabanını kapat
                
                # Az önce kaydettiğimiz veriyi "son kaydedilen" olarak hafızaya al ki bir sonraki sefer aynıysa tekrar yazmasın.
                son_kaydedilen_veri = mevcut_ozet
                print(f"[Karakutu] Veri Kaydedildi: {anlik_veri}")
            
            # --- ACİL DURUM VE SINIR İHLALİ (GEOFENCING) KONTROLÜ ---
            lat = anlik_veri["enlem"]
            lon = anlik_veri["boylam"]
            
            # Eğer koordinatlar 0 ise (GPS uyduları kaybettiyse)
            if lat == 0 or lon == 0:
                hata_mesaji = {"durum": "GPS Bağlantısı Koptu", "hata_kodu": 404}
                # 'acil_durum' kuyruğuna hata mesajını bas. (Arayüz bunu duyduğunda ekranda kırmızı uyarı verir).
                ch.basic_publish(exchange='', routing_key='acil_durum', body=json.dumps(hata_mesaji))
                
            # Eğer dron belirlenen sanal kafesin (Geofence - Belirli bir Enlem/Boylam sınırının) dışına çıktıysa
            # (Örneğin test sahamız: Enlem 39.88 ile 39.91 arası, Boylam 32.76 ile 32.79 arası ODTÜ/Bilkent ormanı vs.)
            elif lat < 39.8800 or lat > 39.9100 or lon < 32.7600 or lon > 32.7900:
                hata_mesaji = {"durum": "Sınır İhlali Tespit Edildi", "hata_kodu": 101}
                ch.basic_publish(exchange='', routing_key='acil_durum', body=json.dumps(hata_mesaji))
              
        except Exception as e:
            # Gelen bozuk bir mesaj yüzünden Thread çökmesin diye hatayı ekrana basıp yola devam et.
            print("Veri okuma hatası:", e)
   
    # 'telemetri_kuyrugu'nu dinlemeye başla ve mesaj geldikçe yukarıdaki 'callback' fonksiyonunu çalıştır.
    channel.basic_consume(queue='telemetri_kuyrugu', on_message_callback=callback, auto_ack=True)
    channel.start_consuming() # Dinleme döngüsünü başlat (Sonsuz)

# Yukarıdaki veritabanı dinleme servisini, Flask web sunucusunu kilitlememesi için ayrı bir iş parçacığında (Thread) başlat.
threading.Thread(target=rabbitmq_dinle, daemon=True).start()

# --- FLASK WEB API (REST ENDPOINT) TANIMLAMALARI ---

# Arayüzden (Angular) komut göndermek için kullanılacak API Ucu (URL: http://localhost:5000/api/komut)
# Sadece POST (Veri Gönderme) isteklerine cevap verir.
@app.route('/api/komut', methods=['POST'])
def komut_al():
    """Arayüzden (Angular HttpClient üzerinden) gelen komutları alır ve RabbitMQ'daki 'komut_kuyrugu'na postalar."""
    # Arayüzden gelen HTTP gövdesindeki JSON'u Python sözlüğüne çevir.
    veri = request.json
    # Sözlüğün içindeki 'komut' (Örn: 'RTL') değerini çek.
    komut = veri.get("komut")
    
    if komut:
        # Eğer geçerli bir komut geldiyse, doğrudan RabbitMQ'ya bağlan
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue='komut_kuyrugu', durable=False)
        
        # Komutu RabbitMQ'nun komut kuyruğuna yayınla. (Bunu esp_bridge.py yakalayıp ESP32'ye iletecek).
        channel.basic_publish(
            exchange='', 
            routing_key='komut_kuyrugu', 
            body=json.dumps({"komut": komut})
        )
        connection.close()
        
        # Arayüze "İşlem Başarılı (200 OK)" cevabı dön.
        return jsonify({"durum": "basarili", "mesaj": f"{komut} komutu iletildi"})
        
    # Eğer boş veya hatalı istek atıldıysa "Hata (400 Bad Request)" dön.
    return jsonify({"durum": "hata", "mesaj": "Komut bulunamadı"}), 400

# Arayüzdeki 'Karakutu (Uçuş Veri Kayıtları)' tablosuna veri sağlamak için API Ucu (URL: http://localhost:5000/api/gecmis)
@app.route('/api/gecmis', methods=['GET'])
def gecmis_verileri_getir():
    # URL'den limit ve filtre parametrelerini al
    limit = request.args.get('limit', 20, type=int)
    filtre = request.args.get('filtre', 'tumu') # Angular'dan gelen filtre tipini al
    
    try:
        conn = sqlite3.connect('ucus_verileri.db', timeout=10)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        # Gelen filtreye göre dinamik SQL (Veritabanı) sorgusu oluşturuyoruz:
        if filtre == 'alarmlar':
            # EĞER FİLTRE ALARMS İSE: Durumu 'NORMAL' olmayan kayıtları getir.
            sorgu = "SELECT * FROM telemetri WHERE durum != 'NORMAL' ORDER BY id DESC LIMIT ?"
        else:
            # EĞER FİLTRE TÜMÜ İSE: Hiçbir şart koşmadan her şeyi getir.
            sorgu = "SELECT * FROM telemetri ORDER BY id DESC LIMIT ?"
            
        cursor.execute(sorgu, (limit,))
        satirlar = cursor.fetchall()
        conn.close()
        
        # Sonuçları JSON'a çevirip Angular'a yolla
        veriler = [dict(satir) for satir in satirlar]
        return jsonify(veriler), 200
    except Exception as e:
        print(f"Veritabanı okuma hatası: {e}")
        return jsonify({"durum": "hata", "mesaj": "Veritabanına ulaşılamadı"}), 500
    
@app.route('/api/export/csv', methods=['GET'])
def csv_disa_aktar():
    try:
        conn = sqlite3.connect('ucus_verileri.db', timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM telemetri ORDER BY id DESC")
        satirlar = cursor.fetchall()
        conn.close()

        def generate():
            data = StringIO()
            # 1. YENİ EK: Excel'in Türkçe karakterleri (ş,ğ,ı) bozmadan okuması için UTF-8 BOM damgası ekliyoruz
            data.write('\ufeff') 
            
            # 2. YENİ EK: Excel verileri düzgün sütunlara bölsün diye ayracı noktalı virgül (;) yapıyoruz
            writer = csv.writer(data, delimiter=';')
            
            if satirlar:
                writer.writerow(satirlar[0].keys())
                yield data.getvalue()
                data.seek(0)
                data.truncate(0)
            for satir in satirlar:
                writer.writerow(dict(satir).values())
                yield data.getvalue()
                data.seek(0)
                data.truncate(0)

        return Response(generate(), mimetype='text/csv', headers={
            "Content-Disposition": "attachment; filename=ucus_kara_kutu_raporu.csv"
        })
    except Exception as e:
        return jsonify({"hata": str(e)}), 500   
    
    

# Eğer bu dosya (app.py) terminalden direkt çalıştırılmışsa:
if __name__ == '__main__':
    # Flask web sunucusunu 5000 portunda başlat.
    # use_reloader=False yapıyoruz çünkü arka planda çalışan RabbitMQ dinleyici Thread'inin 
    # Flask'ın otomatik yenileme (reload) sistemi yüzünden iki kere başlatılıp çökmesine engel olmamız lazım.
    app.run(debug=True, port=5000, use_reloader=False)