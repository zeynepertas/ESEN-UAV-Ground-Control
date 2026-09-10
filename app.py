from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import pika
import json
import threading
import sqlite3
from datetime import datetime
from config import RABBITMQ_URL
import csv
from io import StringIO

class DatabaseManager:
    def __init__(self, db_name='ucus_verileri.db'):
        self.db_name = db_name
        self._init_db()
        self._run_migrations()

    def _init_db(self):
        conn = sqlite3.connect(self.db_name, timeout=10)
        cursor = conn.cursor()
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
                ax REAL, ay REAL, az REAL,
                gx REAL, gy REAL, gz REAL,
                roll REAL, pitch REAL, yaw REAL,
                mx REAL, my REAL, mz REAL
            )
        ''')
        conn.commit()
        conn.close()

    def _run_migrations(self):
        columns = [
            "durum TEXT", "sicaklik REAL", 
            "ax REAL", "ay REAL", "az REAL",
            "gx REAL", "gy REAL", "gz REAL",
            "roll REAL", "pitch REAL"
        ]
        for col in columns:
            try:
                conn = sqlite3.connect(self.db_name, timeout=10)
                conn.execute(f"ALTER TABLE telemetri ADD COLUMN {col}")
                conn.commit()
                conn.close()
            except:
                pass

    def insert_telemetry(self, data):
        conn = sqlite3.connect(self.db_name, timeout=10)
        cursor = conn.cursor()
        su_an = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
            INSERT INTO telemetri (zaman, irtifa, hiz, enlem, boylam, durum, sicaklik, ax, ay, az, gx, gy, gz, roll, pitch, yaw, mx, my, mz)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            su_an, data.get("irtifa", 0), data.get("hiz", 0), data.get("enlem", 0), 
            data.get("boylam", 0), data.get("durum", "NORMAL"), data.get("sicaklik", 0),
            data.get("ax", 0), data.get("ay", 0), data.get("az", 0),
            data.get("gx", 0), data.get("gy", 0), data.get("gz", 0),
            data.get("roll", 0), data.get("pitch", 0), data.get("yaw", 0),
            data.get("mx", 0), data.get("my", 0), data.get("mz", 0)
        ))
        conn.commit()
        conn.close()

    def get_history(self, limit, filter_type):
        conn = sqlite3.connect(self.db_name, timeout=10)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        if filter_type == 'alarmlar':
            sorgu = "SELECT * FROM telemetri WHERE durum != 'NORMAL' ORDER BY id DESC LIMIT ?"
        else:
            sorgu = "SELECT * FROM telemetri ORDER BY id DESC LIMIT ?"
            
        cursor.execute(sorgu, (limit,))
        satirlar = cursor.fetchall()
        conn.close()
        return [dict(satir) for satir in satirlar]
        
    def get_all_for_csv(self):
        conn = sqlite3.connect(self.db_name, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM telemetri ORDER BY id DESC")
        satirlar = cursor.fetchall()
        conn.close()
        return satirlar


class RabbitMQListener:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.anlik_veri = {"irtifa": 0, "hiz": 0}
        self.son_kaydedilen_veri = None

    def start(self):
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue='telemetri_kuyrugu', durable=True)
        channel.queue_declare(queue='acil_durum', durable=True)

        def callback(ch, method, properties, body):
            try:
                veri = json.loads(body)
                self._update_current_data(veri)
                
                # Veritabanına kaydet
                self.db_manager.insert_telemetry(self.anlik_veri)
                print(f"[Karakutu] Veri Kaydedildi: {self.anlik_veri}")
                
                # Geofencing ve Acil Durum Kontrolü
                self._check_geofence(ch)
                
            except Exception as e:
                print("Veri okuma hatası:", e)

        channel.basic_consume(queue='telemetri_kuyrugu', on_message_callback=callback, auto_ack=True)
        channel.start_consuming()

    def _update_current_data(self, veri):
        keys = ["irtifa", "hiz", "enlem", "boylam", "durum", "sicaklik", 
                "ax", "ay", "az", "gx", "gy", "gz", "roll", "pitch", "yaw", "mx", "my", "mz"]
        
        for k in keys:
            if k in ["irtifa", "hiz"]:
                self.anlik_veri[k] = veri.get(k, self.anlik_veri.get(k, 0))
            elif k == "durum":
                self.anlik_veri[k] = veri.get(k, "NORMAL")
            else:
                self.anlik_veri[k] = veri.get(k, 0)

    def _check_geofence(self, channel):
        lat = self.anlik_veri["enlem"]
        lon = self.anlik_veri["boylam"]
        
        if lat == 0 or lon == 0:
            hata_mesaji = {"durum": "GPS Bağlantısı Koptu", "hata_kodu": 404}
            channel.basic_publish(exchange='', routing_key='acil_durum', body=json.dumps(hata_mesaji))
        elif lat < 39.8800 or lat > 39.9100 or lon < 32.7600 or lon > 32.7900:
            hata_mesaji = {"durum": "Sınır İhlali Tespit Edildi", "hata_kodu": 101}
            channel.basic_publish(exchange='', routing_key='acil_durum', body=json.dumps(hata_mesaji))


class FlaskAPI:
    def __init__(self, db_manager):
        self.app = Flask(__name__)
        CORS(self.app, resources={r"/api/*": {"origins": ["http://localhost:4200", "http://127.0.0.1:4200"]}})
        self.db_manager = db_manager
        self._setup_routes()

    def _setup_routes(self):
        self.app.add_url_rule('/api/komut', 'komut_al', self.komut_al, methods=['POST'])
        self.app.add_url_rule('/api/gecmis', 'gecmis_verileri_getir', self.gecmis_verileri_getir, methods=['GET'])
        self.app.add_url_rule('/api/export/csv', 'csv_disa_aktar', self.csv_disa_aktar, methods=['GET'])

    def komut_al(self):
        veri = request.json
        komut = veri.get("komut")
        
        if komut:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel = connection.channel()
            channel.queue_declare(queue='komut_kuyrugu', durable=False)
            
            channel.basic_publish(
                exchange='', 
                routing_key='komut_kuyrugu', 
                body=json.dumps({"komut": komut})
            )
            connection.close()
            return jsonify({"durum": "basarili", "mesaj": f"{komut} komutu iletildi"})
            
        return jsonify({"durum": "hata", "mesaj": "Komut bulunamadı"}), 400

    def gecmis_verileri_getir(self):
        limit = request.args.get('limit', 20, type=int)
        filtre = request.args.get('filtre', 'tumu')
        
        try:
            veriler = self.db_manager.get_history(limit, filtre)
            return jsonify(veriler), 200
        except Exception as e:
            print(f"Veritabanı okuma hatası: {e}")
            return jsonify({"durum": "hata", "mesaj": "Veritabanına ulaşılamadı"}), 500

    def csv_disa_aktar(self):
        try:
            satirlar = self.db_manager.get_all_for_csv()

            def generate():
                data = StringIO()
                data.write('\ufeff') 
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

    def run(self):
        self.app.run(debug=True, port=5000, use_reloader=False)


if __name__ == '__main__':
    db_manager = DatabaseManager()
    
    rabbitmq_listener = RabbitMQListener(db_manager)
    rabbitmq_listener.start()
    
    flask_api = FlaskAPI(db_manager)
    flask_api.run()