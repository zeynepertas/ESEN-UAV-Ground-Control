import socket # Ağ üzerinden TCP/IP bağlantısı kurabilmek için gerekli Python çekirdek kütüphanesi
import threading # Arka planda aynı anda birden fazla işi (dinleme, yollama) yapabilmek için eşzamanlılık (iş parçacığı) kütüphanesi
import pika # RabbitMQ (Mesaj Kuyruğu) sunucusuna bağlanıp STOMP ve AMQP protokollerini kullanmak için gereken kütüphane
import json # Verileri ağ üzerinde gönderirken sözlükleri (dictionary) metin formatına (JSON) çevirmek için kütüphane
import time # Bekleme (sleep) ve zaman hesaplamaları yapabilmek için zaman kütüphanesi
import requests # Eğer dışarıdan bir HTTP API çağırmamız gerekirse diye ekli (şu an aktif kullanılmıyor)
from config import RABBITMQ_URL # config.py dosyasından RabbitMQ sunucusunun adresini ve şifresini içeri aktarıyoruz

# ESP32'den gelen son değerleri tuttuğumuz küresel (global) sözlük.
# Başlangıçta henüz veri gelmediği için her şeyi sıfır (0) veya başlangıç durumunda kabul ediyoruz.
anlik_veri = {
    "irtifa": 0.0,      # İHA'nın deniz seviyesinden yüksekliği (GPS üzerinden gelen rakım bilgisi)
    "hiz": 0.0,         # İHA'nın yer hızı (Ground Speed). Şu an ESP'den GPS hızı yollanmadığı için 0 tutuyoruz.
    "enlem": 0.0,       # GPS üzerinden gelen Enlem (Latitude) koordinatı (Ondalık formatta)
    "boylam": 0.0,      # GPS üzerinden gelen Boylam (Longitude) koordinatı (Ondalık formatta)
    "durum": "NORMAL",  # İHA'nın güncel uçuş modu (Örn: NORMAL, RTL, TAKEOFF). Varsayılan olarak NORMAL.
    "zemin_rakimi": 0.0,# Yerin yüksekliği (İleride radar altimetresi takılırsa çarpışma hesabı için, şu an 0)
    "ax": 0,            # MPU6050'nin X eksenindeki fiziksel ivme değeri (g cinsinden)
    "ay": 0,            # MPU6050'nin Y eksenindeki fiziksel ivme değeri (g cinsinden)
    "az": 0,            # MPU6050'nin Z eksenindeki fiziksel ivme değeri (Normalde masada dururken 1G veya -1G'dir)
    "gx": 0,            # MPU6050'nin X eksenindeki jiroskop (dönüş hızı) verisi (derece/saniye)
    "gy": 0,            # MPU6050'nin Y eksenindeki jiroskop verisi
    "gz": 0,            # MPU6050'nin Z eksenindeki jiroskop verisi
    "sicaklik": 0.0,    # MPU6050 içindeki dahili sıcaklık sensörünün okuduğu Celcius değeri
    "roll": 0.0,        # Arduino'daki Tamamlayıcı Filtre (Complementary Filter) ile hesaplanan Yatış açısı (Roll)
    "pitch": 0.0        # Arduino'da hesaplanan Yunuslama açısı (Pitch)
}

# ESP32'nin TCP üzerinden bize bağlanıp bağlamadığını tutan değişken.
# Eğer bağlıysa (soket açıksa), bu değişken üzerinden ESP'ye komut (Örn: "TAKEOFF\n") fırlatacağız.
aktif_soket_baglantisi = None

def nmea_to_decimal(nmea_str):
    """
    Arduino'dan (GPS modülünden) gelen ham NMEA (National Marine Electronics Association) 
    formatındaki koordinatları (Örn: 3953.500)
    Google Haritalar, Leaflet gibi harita kütüphanelerinin anlayacağı 
    Ondalık Derece (Decimal Degrees) formatına (Örn: 39.8916) çeviren matematiksel fonksiyon.
    """
    # Eğer gelen metin boşsa, None ise veya direkt "0" ise (yani GPS henüz uydulara kilitlenmediyse)
    if not nmea_str or nmea_str == "0" or nmea_str == "":
        return 0.0 # Çevirmeye uğraşma, direkt 0 koordinatını döndür (Güvenlik önlemi)
    try:
        sign = 1 # Yön belirteci. Kuzey(N) ve Doğu(E) pozitiftir.
        
        # Eğer koordinat metninin başında eksi (-) varsa bu Güney (S) veya Batı (W) yarımküreyi temsil eder.
        if nmea_str.startswith('-'):
            sign = -1 # Yön belirtecini negatif (-1) yap
            nmea_str = nmea_str[1:] # Metnin başındaki eksiyi sil ki matematiği bozmasın
        elif nmea_str.startswith('+'):
            nmea_str = nmea_str[1:] # Eğer artı (+) ile geliyorsa sadece artıyı sil
            
        # Temizlenmiş (sadece rakam ve virgül kalan) metni virgüllü (kesirli) sayı formuna (float) çevir
        val = float(nmea_str)
        
        # NMEA formatında, virgülden önceki sayının ilk iki (veya boylamda üç) hanesi DERECE (Degree), 
        # geri kalan kısım ise DAKİKA (Minute) olarak gelir. 
        # Örnek: 3953.500 sayısını 100'e bölersek 39.53500 olur. 
        # int() ile bunu tam sayıya çevirirsek '39' dereceyi elde ederiz.
        degrees = int(val / 100)
        
        # Orijinal sayıdan (3953.500), bulduğumuz derecenin yüz katını (3900) çıkarırsak, 
        # elimizde sadece dakikalar (53.500) kalır.
        minutes = val - (degrees * 100)
        
        # Dakikaları 60'a bölüp ondalık kısma çeviriyoruz (çünkü 1 derece = 60 dakikadır).
        # Derece ile toplayıp, en baştaki yön (sign) ile çarparak nihai koordinatı buluyoruz.
        return sign * (degrees + (minutes / 60.0))
    except:
        # Eğer yukarıdaki matematik işlemlerinden birinde bir hata (Exception) oluşursa 
        # (Örneğin harf gelmesi veya boşluk kalması), programın çökmemesi (crash yememesi) için
        # hatayı yut (catch) ve sıfır koordinatına (0.0) dön.
        return 0.0

def rabbitmq_komut_dinleyici():
    """
    Bu fonksiyon arka planda (ayrı bir thread'de) sürekli olarak çalışıp,
    Arayüzdeki (Angular) butonlara (RTL, LAND, JOYSTICK vb.) basıldığında
    RabbitMQ'ya düşen mesajları yakalayarak ESP32'ye iletir.
    """
    # Ana programdaki küresel değişkenleri (socket bağlantısı ve anlık veriyi) kullanacağımızı belirtiyoruz
    global aktif_soket_baglantisi, anlik_veri
    
    while True: # Sunucu çökerse veya bağlantı koparsa pes etmemek için sonsuz bir ana döngü
        try:
            # Pika kütüphanesini kullanarak RabbitMQ sunucusuna (broker) bağlanıyoruz
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            # Bağlantı üzerinden haberleşmek için bir sanal kanal (channel) açıyoruz
            channel = connection.channel()
            # Komutların birikeceği 'komut_kuyrugu' adında bir kuyruk (queue) deklare ediyoruz.
            # durable=False diyerek, sunucu resetlenirse eski komutların silinmesini sağlıyoruz (Eski komutu uygulamak dronu düşürür)
            channel.queue_declare(queue='komut_kuyrugu', durable=False)

            def komut_geldi(ch, method, properties, body):
                # Bu alt fonksiyon (callback), RabbitMQ'ya bir mesaj düştüğü an otomatik tetiklenir
                global aktif_soket_baglantisi, anlik_veri
                
                # Gelen mesajın gövdesini (body), bytes (byte dizisi) halinden alıp
                # json.loads ile Python'un anlayacağı sözlük (dict) formatına çeviriyoruz.
                veri = json.loads(body)
                
                # Sözlüğün içinden "komut" anahtarına sahip metni çekiyoruz (Örn: 'RTL')
                komut = veri.get("komut") 
                
                # Konsola komutun geldiğini logluyoruz
                print(f"[RabbitMQ -> ESP32] Komut alındı: {komut}")
                
                # --- ARAYÜZÜN (Karakutunun) ANINDA TEPKİ VERMESİ İÇİN ---
                # Arayüzdeki uçuş modunun (NORMAL, RTL vb.) saniyesinde değişmesi için,
                # ESP32'den teyit gelmesini beklemeden kendi yerel anlık verimizi güncelliyoruz.
                if komut == "RTL":
                    anlik_veri["durum"] = "RTL"
                elif komut == "EMERGENCY_STOP":
                    anlik_veri["durum"] = "EMERGENCY_STOP"
                elif komut == "LAND":
                    anlik_veri["durum"] = "LAND"
                elif komut == "TAKEOFF":
                    anlik_veri["durum"] = "TAKEOFF"
                elif komut in ["NORTH", "SOUTH", "EAST", "WEST"]:
                    # Eğer manuel bir joystick komutu geldiyse (Kuzey, Güney vb.), 
                    # İHA artık Otonom'dan Manuel uçuşa geçmiş demektir.
                    anlik_veri["durum"] = "MANUAL" 
                
                # --- KOMUTUN DRONA (ESP32) İLETİLMESİ ---
                # Eğer TCP soketi üzerinden bağlanmış aktif bir ESP32 donanımımız varsa:
                if aktif_soket_baglantisi:
                    try:
                        # Arduino kodunda "readStringUntil('\n')" kullandığımız için,
                        # komutun sonuna mutlaka \n (Alt Satıra Geç - New Line) karakteri ekliyoruz!
                        mesaj = f"{komut}\n"
                        # Python'daki metinleri ağa (TCP) gönderirken byte formatına (UTF-8) çevirmemiz (encode) şarttır.
                        aktif_soket_baglantisi.sendall(mesaj.encode('utf-8'))
                        print(f"  -> ESP32'ye başarıyla iletildi.")
                    except Exception as e:
                        # Eğer ESP32 menzilden çıktıysa, Wi-Fi koptuysa veya bataryası bittiyse hata verecektir
                        print(f"  -> ESP32'ye iletilirken hata: {e}")
                        # Bağlantı fiziksel olarak koptuğu için aktif soketi None (Yok) yapıyoruz
                        aktif_soket_baglantisi = None 
                else:
                    # Soket bağlı değilse (ESP açık değilse) komutun heba olduğunu kullanıcıya bildiriyoruz
                    print("  -> Uyarı: ESP32 henüz bağlı değil, arayüzden gelen komut çöpe gitti!")

            # Kanalımıza "komut_kuyrugu"na abone olduğumuzu (consume) bildiriyoruz. 
            # Mesaj gelince 'komut_geldi'yi çalıştır, 'auto_ack=True' ile mesajı işledikten sonra kuyruktan hemen sil diyoruz.
            channel.basic_consume(queue='komut_kuyrugu', on_message_callback=komut_geldi, auto_ack=True)
            print("[RabbitMQ] Arayüzdeki komut butonları dinleniyor...")
            
            # channel.start_consuming() diyerek bu thread'i (iş parçacığını) sonsuz bir dinleme döngüsüne sokuyoruz. 
            channel.start_consuming() 
        except Exception as e:
            # Eğer RabbitMQ Docker container'ı kapanırsa, programın çökmemesi için hatayı yakala
            print(f"[RabbitMQ] Komut Dinleyici Hatası: {e}. 5 saniye sonra tekrar denenecek...")
            time.sleep(5) # Sunucuya hemen saldırıp (spam yapıp) CPU'yu yormamak için 5 saniye bekle

def rabbitmq_telemetri_gonderici():
    """
    Bu fonksiyon ayrı bir arka plan iş parçacığında çalışır (Thread).
    Görevi: ESP32'den gelen ve 'anlik_veri' sözlüğünde güncellenen 
    sensör değerlerini her saniyede bir paketleyip RabbitMQ üzerinden Arayüze ve Veritabanı API'sine yaymaktır (Broadcasting).
    """
    global anlik_veri
    while True: # RabbitMQ kapanırsa pes etmemesi için sonsuz dış döngü
        try:
            # RabbitMQ sunucusuna bağlanmak için Pika bağlantısı kur
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel = connection.channel()
            
            # Bu kez 'telemetri_kuyrugu'nu deklare ediyoruz. 
            # durable=True demek, RabbitMQ sunucusu kapanıp açılsa bile bu kuyruk (ve içindeki önemli veriler) diskte saklanır, silinmez.
            channel.queue_declare(queue='telemetri_kuyrugu', durable=True)
            
            while True: # Bağlantı kurulduğunda sürekli olarak veri basacağımız iç döngü
                # 'anlik_veri' içindeki değerleri doğrudan yollamak yerine 'round' fonksiyonu ile
                # virgülden sonra 2 veya 5 basamak kalacak şekilde yuvarlıyoruz (Örn: 3.14159265 -> 3.14)
                # Bu işlem, ağdaki veri trafiğini azaltır ve arayüzün (Angular) daha az yorulmasını sağlar.
                temiz_veri = {
                    "irtifa": round(anlik_veri["irtifa"], 2),
                    "hiz": round(anlik_veri["hiz"], 2),
                    "enlem": round(anlik_veri["enlem"], 5), # Koordinatlar hassas olduğu için 5 basamak
                    "boylam": round(anlik_veri["boylam"], 5),
                    "durum": anlik_veri["durum"], # Durum zaten metin olduğu için yuvarlanmaz
                    "zemin_rakimi": round(anlik_veri["zemin_rakimi"], 2),
                    "ax": anlik_veri["ax"], # ESP'den zaten 3 basamak yuvarlanmış geldiği için direkt alıyoruz
                    "ay": anlik_veri["ay"],
                    "az": anlik_veri["az"],
                    "gx": anlik_veri["gx"],
                    "gy": anlik_veri["gy"],
                    "gz": anlik_veri["gz"],
                    "sicaklik": round(anlik_veri["sicaklik"], 2),
                    "roll": round(anlik_veri["roll"], 2),
                    "pitch": round(anlik_veri["pitch"], 2)
                }
                
                # Elde ettiğimiz bu temiz sözlüğü JSON (metin tabanlı veri formatı) dosyasına çeviriyoruz.
                mesaj_bedeni = json.dumps(temiz_veri)
                
                # Kanal üzerinden (basic_publish) bu mesajı kuyruğa postalıyoruz (yayınlıyoruz).
                # exchange='' diyerek doğrudan 'telemetri_kuyrugu' routing_key'ine basıyoruz.
                channel.basic_publish(
                    exchange='',
                    routing_key='telemetri_kuyrugu',
                    body=mesaj_bedeni
                )
                
                # Konsolda verinin aktığını (kalp atışını) görmek için print ile ekrana basıyoruz.
                print(f"[Telemetri] Arayüze Gönderildi: {temiz_veri}")
                
                # Sistemin deli gibi saniyede binlerce kez çalışıp CPU'yu yakmasını engellemek için
                # tam 1 saniye (1000 milisaniye) uykuya (sleep) dalmasını sağlıyoruz. (Bu 1 Hz Telemetri Hızı demektir).
                time.sleep(1) 
        except Exception as e:
            # Eğer ağ hatası olur da RabbitMQ koparsa, çökmeyi engelle ve 5 saniye sonra dış döngüden tekrar dene
            print(f"[RabbitMQ] Telemetri Gönderici Hatası: {e}. 5 saniye sonra tekrar denenecek...")
            time.sleep(5)

def tcp_sunucu_baslat():
    """
    Bu fonksiyon Python programının kalbidir (Ana Thread).
    Görevleri:
    1. Bilgisayarda bir TCP/IP Portu (Kapısı) açmak.
    2. ESP32'nin Wi-Fi üzerinden bu kapıya gelip bağlanmasını beklemek (Listening).
    3. Bağlandıktan sonra ESP'den akan metin verilerini (GPS ve MPU) saniyede yüzlerce kez durmadan okumak.
    """
    global anlik_veri, aktif_soket_baglantisi
    
    # TCP soketi oluşturuluyor. 
    # AF_INET -> IPv4 adreslemesini (192.168... gibi) kullan. 
    # SOCK_STREAM -> Veri garantili TCP protokolünü kullan (Kayıpsız veri aktarımı).
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # SO_REUSEADDR parametresi: Eğer programı Ctrl+C ile kapatıp hızlıca tekrar açarsan, 
    # işletim sistemi "Bu port hala meşgul!" demez, portu zorla tekrar sana tahsis eder.
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    host = '0.0.0.0' # 0.0.0.0 demek, bilgisayarın sahip olduğu TÜM ağ bağdaştırıcılarını (Wi-Fi, Ethernet vb.) dinle demektir.
    port = 5001      # Arduino'daki wifiClient.connect(..., 5001) kodundaki hedef kapı numarası.
    
    # Soketi belirttiğimiz IP ve Port'a bağlıyoruz.
    server_socket.bind((host, port))
    
    # Gelen bağlantı isteklerini sıraya dizip dinlemeye başlıyoruz. (1 parametresi: Aynı anda kuyrukta 1 bağlantı bekleyebilir)
    server_socket.listen(1)
    print(f"[TCP Sunucu] {port} portunda ESP32'nin bağlanması bekleniyor...")
    
    while True: # Bir ESP32 bağlansa, sonra kopsa bile sunucu kapanmasın, yeni bir bağlantı beklesin diye dış döngü.
        
        # server_socket.accept() programı burada kilitler (bloke eder)! 
        # Ta ki ESP32 Wi-Fi üzerinden "Ben geldim" diyene kadar program alt satıra geçmez.
        client_socket, addr = server_socket.accept() 
        
        # Biri bağlandığı anda kilit açılır. Bağlanan cihazın IP adresi (addr) ekrana basılır.
        print(f"[TCP Sunucu] ESP32 Başarıyla Bağlandı! Gelen Adres: {addr}")
        
        # Yukarıda komut gönderici fonksiyonumuz ESP32'ye mesaj atabilsin diye, 
        # bu yeni kurulan sağlam köprüyü (soketi) global değişkene kopyalıyoruz.
        aktif_soket_baglantisi = client_socket 
        
        try:
            buffer = "" # ESP32'den gelen byte'ları parça parça biriktireceğimiz geçici havuz (tampon bellek)
            
            while True: # ESP32 bağlı kaldığı sürece sonsuza kadar dönecek iç okuma döngüsü
                
                # recv(1024) -> Ağ kartından maksimum 1024 byte (karakter) veriyi çek (oku). 
                data = client_socket.recv(1024)
                
                if not data: 
                    # Eğer data değişkeni boş (null/empty) dönerse, bu TCP protokolünde karşı tarafın (ESP32)
                    # fiziksel olarak bağlantıyı kapattığı, koptuğu veya elektriğinin kesildiği anlamına gelir.
                    print("[TCP Sunucu] ESP32 bağlantıyı kapattı (Wi-Fi koptu veya cihaz resetlendi).")
                    break # İç döngüyü kırıp dış döngüye dön (Yeniden bağlanmasını bekle)
                    
                # Gelen veriler ağda 'bytes' (010101) formatındadır. 
                # decode('utf-8') ile bunu insanların ve Python'un okuyabileceği String (metin) formatına çeviriyoruz.
                # Çevrilen metni havuzun sonuna ekliyoruz (buffer +=).
                buffer += data.decode('utf-8')
                
                # Arduino kodunda verileri yollarken wifiClient.print("...\n") şeklinde yolladık.
                # Yani her bir tam mesajın (satırın) sonuna "Alt Satıra Geç" (\n) karakteri (Enter tuşu) ekledik.
                # Eğer havuzda bir '\n' harfi varsa, demek ki ESP32 tam bir cümle söylemiştir.
                while '\n' in buffer:
                    # split('\n', 1) komutu metni bulduğu ilk '\n' karakterinden tam ikiye böler.
                    # 1. parça (line): Tamamlanmış cümle.
                    # 2. parça (buffer): Cümlenin devamında yanlışlıkla gelmiş yarım kelimeler (yeni havuza aktarılır).
                    line, buffer = buffer.split('\n', 1)
                    
                    # Cümlenin başındaki ve sonundaki fazladan görünmez boşlukları (space, \r) temizle
                    line = line.strip() 
                    
                    # Eğer gelen tam cümlenin başı "GPS," ile başlıyorsa, bu bir Konum bilgisidir.
                    if line.startswith("GPS,"):
                        print(f"[ESP32 -> TCP Sunucu] GPS Verisi Alındı: {line}")
                        
                        # Cümleyi virgüllerden (,) keserek bir kelime dizisi (liste) oluştur.
                        # Örnek: ["GPS", "3953.500", "03248.100", "120.5", "8"]
                        parcalar = line.split(",")
                        
                        # Listede en az 4 parça (GPS, Enlem, Boylam, Rakım vb.) olduğundan emin ol (Eksik veri kontrolü)
                        if len(parcalar) >= 4:
                            ham_enlem = parcalar[1]
                            ham_boylam = parcalar[2]
                            ham_rakim = parcalar[3]
                            
                            # Eğer enlem ve boylam metinleri boş değilse
                            if ham_enlem and ham_boylam:
                                # Yukarıda yazdığımıznmea_to_decimal fonksiyonu ile NMEA koordinatlarını ondalığa çevir.
                                n_enlem = nmea_to_decimal(ham_enlem)
                                n_boylam = nmea_to_decimal(ham_boylam)
                                
                                # Cihaz evin içindeyse veya GPS henüz uydu bulamadıysa koordinat 0.0 döner.
                                # Eğer koordinat 0.0 DEĞİLSE, yani gerçek bir konum bulduysa küresel veriye kaydet.
                                # (Bunu yapmazsak arayüzdeki harita sürekli Afrika kıyılarına (0,0 noktasına) zıplar).
                                if n_enlem != 0.0 and n_boylam != 0.0:
                                    anlik_veri["enlem"] = n_enlem
                                    anlik_veri["boylam"] = n_boylam
                                
                                try:
                                    # Rakım değerini metinden kesirli sayıya (float) çevirip irtifa olarak kaydet
                                    if ham_rakim and float(ham_rakim) > 0:
                                        anlik_veri["irtifa"] = float(ham_rakim)
                                except:
                                    pass # Çevirirken harf vs. çıkarsa hatayı görmezden gel, irtifa eski halinde kalsın
                                    
                    # Eğer gelen cümlenin başı "MPU," ile başlıyorsa, bu Denge/Sensör (İvme, Jiroskop, Açı) bilgisidir.
                    elif line.startswith("MPU,"):
                        # Saniyede 10 kere geldiği için ekranı çok doldurabilir ama hata ayıklama için yazdırıyoruz.
                        print(f"[ESP32 -> TCP Sunucu] MPU Sensör Verisi Alındı: {line}")
                        
                        # Yine virgüllerden kesiyoruz
                        parcalar = line.split(",")
                        
                        # MPU'dan (Başlık, ax, ay, az, gx, gy, gz, sıcaklık, roll, pitch) olmak üzere 10 parça bekliyoruz.
                        # Ama 8 parça gelse bile çökmeyip okuması için en az 8 şartı koyuyoruz.
                        if len(parcalar) >= 8: 
                            try:
                                # String olan parçaları float (kesirli sayı) formatına çevirerek küresel sözlüğe (anlik_veri) gömüyoruz.
                                anlik_veri["ax"] = float(parcalar[1])
                                anlik_veri["ay"] = float(parcalar[2])
                                anlik_veri["az"] = float(parcalar[3])
                                anlik_veri["gx"] = float(parcalar[4])
                                anlik_veri["gy"] = float(parcalar[5])
                                anlik_veri["gz"] = float(parcalar[6])
                                anlik_veri["sicaklik"] = float(parcalar[7])
                                
                                # Eğer Arduino koduna yeni eklediğimiz Roll ve Pitch de (8. ve 9. indis) geldiyse
                                if len(parcalar) >= 10:
                                    anlik_veri["roll"] = float(parcalar[8])   # Dronun yatış açısı (Ufuk Göstergesi için)
                                    anlik_veri["pitch"] = float(parcalar[9])  # Dronun yunuslama açısı
                            except Exception as e:
                                # Eğer Arduino yanlışlıkla "MPU, 1.2.3.4, a" gibi bozuk veya çevrilemeyen 
                                # bir sayı yollarsa program patlamasın diye hatayı yakala
                                print(f"MPU Ayrıştırma Hatası (Bozuk Veri): {e}")
                                
        except Exception as e:
            # Okuma döngüsü esnasında beklenmeyen çok büyük bir hata çıkarsa buraya düşer.
            print(f"[TCP Sunucu] Bağlantı esnasında beklenmeyen hata: {e}")
        finally:
            # Ne olursa olsun (İster ESP32 kopsun, ister kod hata versin, ister döngü kırılsın)
            # çıkarken (finally blogu) soketi temiz bir şekilde işletim sistemine geri iade et (close).
            client_socket.close()
            # Artık bağlı bir cihaz olmadığı için değişkeni None yap ki komut göndermeye çalışmayalım.
            aktif_soket_baglantisi = None

# Python scripti terminalden (python esp_bridge.py) çalıştırıldığında işletilecek ana komut bloğu.
if __name__ == "__main__":
    # 1. İş Parçacığı: Komut Dinleyiciyi (rabbitmq_komut_dinleyici) ayrı bir arka plan işi olarak başlat.
    # daemon=True: Ana program (TCP Sunucu) kapanırsa, bu arka plan işini de beklemeden acımasızca öldür demektir.
    threading.Thread(target=rabbitmq_komut_dinleyici, daemon=True).start()
    
    # 2. İş Parçacığı: Telemetri Göndericiyi (rabbitmq_telemetri_gonderici) ayrı bir iş olarak başlat.
    threading.Thread(target=rabbitmq_telemetri_gonderici, daemon=True).start()
    
    # 3. İş Parçacığı (Ana (Main) Thread): Ana gövde olarak TCP Sunucusunu çalıştırıp ESP32'yi beklesin.
    # Bu fonksiyon sonsuz bir döngüde olduğu için program burada kilitlenir ve asla kendi kendine kapanmaz.
    tcp_sunucu_baslat()
