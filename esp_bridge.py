import serial 
import threading
import pika
import json
import time
import traceback
from config import RABBITMQ_URL

class TelemetryData:
    def __init__(self):
        self.data = {
            "irtifa": 0.0,
            "hiz": 0.0,
            "enlem": 0.0,
            "boylam": 0.0,
            "durum": "NORMAL",
            "zemin_rakimi": 0.0,
            "ax": 0, "ay": 0, "az": 0,
            "gx": 0, "gy": 0, "gz": 0,
            "sicaklik": 0.0,
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "zaman_damgasi": 0,
            "mx": 0.0, "my": 0.0, "mz": 0.0
        }
        # İş parçacığı (Thread) güvenliği için kilit mekanizması
        self.lock = threading.Lock()

    def update(self, key, value):
        with self.lock:
            self.data[key] = value

    def get_all(self):
        with self.lock:
            return self.data.copy()

    def update_from_gps(self, parcalar):
        if len(parcalar) >= 4:
            ham_enlem, ham_boylam, ham_rakim = parcalar[1], parcalar[2], parcalar[3]
            if ham_enlem and ham_boylam:
                n_enlem = self.nmea_to_decimal(ham_enlem)
                n_boylam = self.nmea_to_decimal(ham_boylam)
                if n_enlem != 0.0 and n_boylam != 0.0:
                    self.update("enlem", n_enlem)
                    self.update("boylam", n_boylam)
            if ham_rakim:
                try:
                    if float(ham_rakim) > 0:
                        self.update("irtifa", float(ham_rakim))
                except Exception:
                    pass

    def update_from_mpu(self, parcalar):
        if len(parcalar) >= 15: 
            try:
                with self.lock:
                    self.data["zaman_damgasi"] = int(parcalar[1])
                    self.data["ax"] = float(parcalar[2])
                    self.data["ay"] = float(parcalar[3])
                    self.data["az"] = float(parcalar[4])
                    self.data["gx"] = float(parcalar[5])
                    self.data["gy"] = float(parcalar[6])
                    self.data["gz"] = float(parcalar[7])
                    self.data["sicaklik"] = float(parcalar[8])
                    self.data["roll"] = float(parcalar[9])  
                    self.data["pitch"] = float(parcalar[10])
                    self.data["yaw"] = float(parcalar[11]) 
                    self.data["mx"] = float(parcalar[12])
                    self.data["my"] = float(parcalar[13])
                    self.data["mz"] = float(parcalar[14])
            except Exception as e:
                print(f"Ayrıştırma Hatası: {e}")

    @staticmethod
    def nmea_to_decimal(nmea_str):
        if not nmea_str or nmea_str == "0" or nmea_str == "":
            return 0.0 
        try:
            sign = 1
            if nmea_str.startswith('-'):
                sign = -1
                nmea_str = nmea_str[1:]
            elif nmea_str.startswith('+'):
                nmea_str = nmea_str[1:] 
            val = float(nmea_str)
            degrees = int(val / 100)
            minutes = val - (degrees * 100)
            return sign * (degrees + (minutes / 60.0))
        except:
            return 0.0

class SerialManager:
    def __init__(self, port="COM4", baud_rate=115200, telemetry_data=None):
        self.port = port
        self.baud_rate = baud_rate
        self.telemetry = telemetry_data
        self.ser = None
        self.is_connected = False

    def send_command(self, command):
        if self.is_connected and self.ser:
            try:
                mesaj = f"{command}\n"
                self.ser.write(mesaj.encode('utf-8'))
                print("  -> ESP32'ye başarıyla iletildi.")
            except Exception as e:
                print(f"  -> ESP32'ye iletilirken hata: {e}")
                self.is_connected = False
        else:
            print("  -> Uyarı: ESP32 henüz bağlı değil, arayüzden gelen komut çöpe gitti!")

    def start_listening(self):
        while True:
            try:
                print(f"[Seri Port] {self.port} portuna bağlanmaya çalışılıyor...")
                self.ser = serial.Serial(self.port, self.baud_rate, timeout=2.0)
                self.is_connected = True
                print(f"[Seri Port] Bağlantı Başarılı! {self.port} dinleniyor...")
                self.telemetry.update("durum", "NORMAL")

                son_mesaj_zamani = time.time()
                ilk_veri_alindi = False

                while True:
                    if self.ser.in_waiting > 0:
                        line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        print(line)
                        
                        son_mesaj_zamani = time.time()
                        ilk_veri_alindi = True
                        
                        if not line:
                            continue
                        else:
                            if self.telemetry.get_all()["durum"] == "SİNYAL KAYBI":
                                self.telemetry.update("durum", "NORMAL")
                                print("[BİLGİ] Veri akışı tekrar sağlandı.")

                        if line.startswith("GPS,"):
                            print(f"[Seri Port] GPS: {line}")
                            try:
                                parcalar = line.split(",")
                                self.telemetry.update_from_gps(parcalar)
                            except Exception as e:
                                print(f"[Seri Port] GPS Ayrıştırma Hatası: {e}")

                        elif line.startswith("MPU,"):
                            parcalar = line.split(",")
                            self.telemetry.update_from_mpu(parcalar)
                    else:
                        su_an = time.time()
                        gecen_sure = su_an - son_mesaj_zamani
                        
                        if (not ilk_veri_alindi and gecen_sure > 10.0) or (ilk_veri_alindi and gecen_sure > 2.0):
                            if self.telemetry.get_all()["durum"] != "SİNYAL KAYBI":
                                self.telemetry.update("durum", "SİNYAL KAYBI")
                                print("\n[UYARI] Arduino'dan veri gelmiyor! (Sinyal Kaybı) Bekleniyor...")
                        time.sleep(0.005)
            except Exception as e:
                print(f"\n[SİSTEM UYARISI] Windows Seri Port bağlantısını anlık olarak kesti (Hata: {e})")
                print("[SİSTEM UYARISI] Çökme engellendi! 3 saniye içinde bağlantı yeniden kurulacak...\n")
                self.telemetry.update("durum", "BAGLANTI KOPTU")
                self.is_connected = False
                time.sleep(3)


class RabbitMQManager:
    def __init__(self, telemetry_data, serial_manager):
        self.telemetry = telemetry_data
        self.serial_manager = serial_manager

    def start_publish_thread(self):
        threading.Thread(target=self._publish_loop, daemon=True).start()

    def start_consume_thread(self):
        threading.Thread(target=self._consume_loop, daemon=True).start()

    def _consume_loop(self):
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
                channel = connection.channel()
                channel.queue_declare(queue='komut_kuyrugu', durable=False)

                def komut_geldi(ch, method, properties, body):
                    veri = json.loads(body)
                    komut = veri.get("komut") 
                    print(f"[RabbitMQ -> ESP32] Komut alındı: {komut}")
                    
                    if komut == "RTL":
                        self.telemetry.update("durum", "RTL")
                    elif komut == "EMERGENCY_STOP":
                        self.telemetry.update("durum", "EMERGENCY_STOP")
                    elif komut == "LAND":
                        self.telemetry.update("durum", "LAND")
                    elif komut == "TAKEOFF":
                        self.telemetry.update("durum", "TAKEOFF")
                    elif komut in ["NORTH", "SOUTH", "EAST", "WEST"]:
                        self.telemetry.update("durum", "MANUAL")
                    
                    self.serial_manager.send_command(komut)

                channel.basic_consume(queue='komut_kuyrugu', on_message_callback=komut_geldi, auto_ack=True)
                print("[RabbitMQ] Arayüzdeki komut butonları dinleniyor...")
                channel.start_consuming() 
            except Exception as e:
                print(f"[RabbitMQ] Komut Dinleyici Hatası: {e}. 5 saniye sonra tekrar denenecek...")
                time.sleep(5)

    def _publish_loop(self):
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
                channel = connection.channel()
                channel.queue_declare(queue='telemetri_kuyrugu', durable=True)
                
                while True:
                    if not self.serial_manager.is_connected:
                        time.sleep(1)
                        continue
                    
                    anlik_veri = self.telemetry.get_all()
                    
                    temiz_veri = {
                        "zaman_damgasi": anlik_veri["zaman_damgasi"],
                        "irtifa": round(anlik_veri["irtifa"], 2),
                        "hiz": round(anlik_veri["hiz"], 2),
                        "enlem": round(anlik_veri["enlem"], 5),
                        "boylam": round(anlik_veri["boylam"], 5),
                        "durum": anlik_veri["durum"],
                        "zemin_rakimi": round(anlik_veri["zemin_rakimi"], 2),
                        "ax": anlik_veri["ax"],
                        "ay": anlik_veri["ay"],
                        "az": anlik_veri["az"],
                        "gx": anlik_veri["gx"],
                        "gy": anlik_veri["gy"],
                        "gz": anlik_veri["gz"],
                        "sicaklik": round(anlik_veri["sicaklik"], 2),
                        "roll": round(anlik_veri["roll"], 2),
                        "pitch": round(anlik_veri["pitch"], 2),
                        "yaw": round(anlik_veri["yaw"], 2),
                        "mx": anlik_veri["mx"],
                        "my": anlik_veri["my"],
                        "mz": anlik_veri["mz"]
                    }
                    
                    mesaj_bedeni = json.dumps(temiz_veri)
                    channel.basic_publish(
                        exchange='',
                        routing_key='telemetri_kuyrugu',
                        body=mesaj_bedeni
                    )
                    print(f"[Telemetri] Arayüze Gönderildi: {temiz_veri}")
                    time.sleep(1) 
            except Exception as e:
                print(f"[RabbitMQ] Telemetri Gönderici Hatası: {e}. 5 saniye sonra tekrar denenecek...")
                time.sleep(5)

class BridgeApp:
    def __init__(self):
        self.telemetry = TelemetryData()
        self.serial_manager = SerialManager(port="COM4", baud_rate=115200, telemetry_data=self.telemetry)
        self.rabbitmq_manager = RabbitMQManager(telemetry_data=self.telemetry, serial_manager=self.serial_manager)

    def run(self):
        self.rabbitmq_manager.start_publish_thread()
        self.rabbitmq_manager.start_consume_thread()
        self.serial_manager.start_listening()

if __name__ == "__main__":
    app = BridgeApp()
    app.run()
