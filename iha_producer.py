import json
import threading
import socket #kablosuz ağ üzerinden tcp bağlantısı
import time
import pika
import requests
from config import RABBITMQ_URL

# --- GLOBAL DEĞİŞKENLER ---
iha_durumu = "NORMAL"
manuel_yon = "NORTH"  # Manuel uçuş için varsayılan yön
aktif_baglanti = None  # ESP32 TCP soket bağlantısını tutacak global değişken

HOST = "172.20.10.12"#pcmin wifi ip adresi
PORT = 5000#arduino ile aynı


def zemin_yuksekligi_getir(lat, lon):# enlem(lat) boylam(lon)
  """Open-Meteo API üzerinden gerçek dünya topoğrafya rakımını çeker."""
  try:
    url = ( #dünyanın her yerinin rakım bilgisiini veren
        f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
    )
    r = requests.get(url, timeout=1.5)
    if r.status_code == 200:
      return r.json()["elevation"][0]
  except:
    pass
  return 885.0

def komut_dinle():
    """RabbitMQ üzerindeki 'komut_kuyrugu'nu dinleyerek yer istasyonundan gelen
    (RTL, LAND, TAKEOFF vb.) komutları yakalar ve ESP32'ye TCP ile iletir.
    """
    global iha_durumu, manuel_yon, aktif_baglanti
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue="komut_kuyrugu", durable=False)

        def komut_geldi(ch, method, properties, body):
            global iha_durumu, manuel_yon, aktif_baglanti
            veri = json.loads(body)
            komut = veri.get("komut", "BİLİNMEYEN")

            if komut == "RTL":
                iha_durumu = "RTL"
                print("\n OTOPİLOT: Eve Dönüş (RTL) başlatıldı!")
            elif komut == "EMERGENCY_STOP":
                iha_durumu = "EMERGENCY_STOP"
                print("\n OTOPİLOT: Acil motor durdurma!")
            elif komut == "LAND":
                iha_durumu = "LAND"
                print("\n OTOPİLOT: Güvenli İniş (LAND) başlatıldı.")
            elif komut == "TAKEOFF":
                iha_durumu = "TAKEOFF_REQUESTED"
                print("\n OTOPİLOT: Kalkış/Devriye isteği alındı...")
            elif komut in ["NORTH", "SOUTH", "EAST", "WEST"]:
                iha_durumu = "MANUAL"
                manuel_yon = komut
                print(f"\n OTOPİLOT: Manuel Uçuş Modu -> Yön: {komut}")

            # Komutu ESP32'ye TCP üzerinden gönder
            if aktif_baglanti:
                try:
                    aktif_baglanti.sendall((komut + "\n").encode("utf-8"))
                    print(f"-> ESP32'ye Komut İletildi: {komut}")
                except Exception as e:
                    print(f"ESP32'ye komut gönderilemedi: {e}")

        channel.basic_consume(
            queue="komut_kuyrugu", on_message_callback=komut_geldi, auto_ack=True
        )
        channel.start_consuming()
        
    except Exception as e:
        print(f"Komut dinleyici hatası: {e}")



def simule_et_ve_gonder():
  """ESP32'den seri port (COM3) üzerinden gelen gerçek MPU ve GPS verilerini okur,
  ayrıştırır (parse eder) ve RabbitMQ 'telemetri_kuyrugu'na basar.
  """
  global iha_durumu

  # Komut dinleme işlemini arka planda (thread içinde) başlatıyoruz
  threading.Thread(target=komut_dinle, daemon=True).start()

  # RabbitMQ bağlantısını kuruyoruz
  connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
  channel = connection.channel()
  channel.queue_declare(queue="telemetri_kuyrugu", durable=True)
  
  
  ## --- TCP SOKET SUNUCUSUNU BAŞLATIYORUZ ---
  server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server_socket.bind((HOST, PORT))
  server_socket.listen(1)  # ESP32'den gelecek tekil bağlantıyı dinlemeye başla
  print( f" Kablosuz Sunucu Başlatıldı! {PORT} portundan ESP32 bağlantısı"
      " bekleniyor...")

# ESP32 sunucuya bağlandığı anda 'conn' (bağlantı nesnesi) ve 'addr' (IP adresi) oluşur
  conn, addr = server_socket.accept()
  print(f" ESP32 Başarıyla Kablosuz Bağlandı! Cihaz IP: {addr}")
  

  try:
    while True:
   # ESP32'den kablosuz gelen verileri parça parça okuyoruz
      veri_paket = conn.recv(1024).decode("utf-8", errors="ignore")
      if not veri_paket:
        break  # Bağlantı koparsa döngüden çık

      # Gelen veriler ard arda gelebileceği için satır satır ayırıyoruz
      satirlar = veri_paket.split("\n")
      for ham_veri in satirlar:
        ham_veri = ham_veri.strip()
        if ham_veri:
          parcalar = ham_veri.split(",")
          veri_tipi = parcalar[0]  # "MPU" veya "GPS"

          anlik_veri = {}

# 1. MPU VERİSİ İSE
          if veri_tipi == "MPU" and len(parcalar) >= 8:
            anlik_veri = {
                "veri_tipi": "MPU",
                "durum": iha_durumu,
                "ax": float(parcalar[1]),
                "ay": float(parcalar[2]),
                "az": float(parcalar[3]),
                "gx": float(parcalar[4]),
                "gy": float(parcalar[5]),
                "gz": float(parcalar[6]),
                "sicaklik": float(parcalar[7]),
            }
            print(f"[KABLOSUZ MPU VERİSİ]: {anlik_veri}")

          # 2. GPS VERİSİ İSE
          elif veri_tipi == "GPS" and len(parcalar) >= 5:
            enlem, boylam, rakim, uydu = (
                parcalar[1],
                parcalar[2],
                parcalar[3],
                parcalar[4],
            )
            try:
              zemin_rakimi = zemin_yuksekligi_getir(
                  float(enlem.replace("+", "").replace("-", "")),
                  float(boylam.replace("+", "").replace("-", "")),
              )
            except:
              zemin_rakimi = 885.0

            anlik_veri = {
                "veri_tipi": "GPS",
                "durum": iha_durumu,
                "enlem": enlem,
                "boylam": boylam,
                "rakim": rakim,
                "uydu_sayisi": uydu,
                "zemin_rakimi": round(zemin_rakimi, 2),
            }
            print(f"[KABLOSUZ GPS VERİSİ]: {anlik_veri}")

          # Anlamlı veriyi RabbitMQ kuyruğuna fırlatıyoruz
          if anlik_veri:
            channel.basic_publish(
                exchange="",
                routing_key="telemetri_kuyrugu",
                body=json.dumps(anlik_veri),
            )

  except KeyboardInterrupt:
    print("\n Bağlantı kullanıcı tarafından sonlandırıldı.")
    conn.close()
    server_socket.close()
    connection.close()


if __name__ == "__main__":
  simule_et_ve_gonder()