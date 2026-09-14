import subprocess
import time
import sys

print("======================================================")
print(" 🚀 ESEN UAV - BÜTÜNLEŞİK BACKEND BAŞLATICI (WRAPPER)")
print("======================================================")

try:
    # 1. Flask API (app.py) dosyasını arka planda ayrı bir alt süreç (subprocess) olarak başlat
    print("[1/2] Flask API (Veritabanı ve Sunucu) ayağa kaldırılıyor...")
    flask_process = subprocess.Popen([sys.executable, "app.py"])

    # Sunucunun portu açması için 2 saniye bekle
    time.sleep(2)

    # 2. ESP/Arduino Bridge (esp_bridge.py) dosyasını alt süreç olarak başlat
    print("[2/2] Arduino Donanım Köprüsü (Telemetri) başlatılıyor...\n")
    bridge_process = subprocess.Popen([sys.executable, "esp_bridge.py"])

    # Ana programı canlı tutarak alt süreçlerin (terminal çıktılarını) ekrana yansıtmasını sağla
    flask_process.wait()
    bridge_process.wait()

except KeyboardInterrupt:
    # Kullanıcı terminalde Ctrl+C'ye bastığında yetim (zombi) process kalmaması için ikisini de güvenle kapat
    print("\n[SİSTEM] Kapatma komutu (Ctrl+C) algılandı. Tüm servisler durduruluyor...")
    flask_process.terminate()
    bridge_process.terminate()
    print("Sistem güvenle kapatıldı. İyi uçuşlar! ✈️")
