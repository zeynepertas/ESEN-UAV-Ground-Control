import subprocess
import time
import sys

class BackendLauncher:
    def __init__(self):
        self.flask_process = None
        self.bridge_process = None

    def print_banner(self):
        print("======================================================")
        print(" 🚀 ESEN UAV - BÜTÜNLEŞİK BACKEND BAŞLATICI (WRAPPER)")
        print("======================================================")

    def start_services(self):
        try:
            print("[1/2] Flask API (Veritabanı ve Sunucu) ayağa kaldırılıyor...")
            self.flask_process = subprocess.Popen([sys.executable, "app.py"])

            # Sunucunun portu açması için 2 saniye bekle
            time.sleep(2)

            print("[2/2] Arduino Donanım Köprüsü (Telemetri) başlatılıyor...\n")
            self.bridge_process = subprocess.Popen([sys.executable, "esp_bridge.py"])

            # Ana programı canlı tutarak alt süreçlerin ekrana yansıtmasını sağla
            self.flask_process.wait()
            self.bridge_process.wait()

        except KeyboardInterrupt:
            self.stop_services()

    def stop_services(self):
        print("\n[SİSTEM] Kapatma komutu (Ctrl+C) algılandı. Tüm servisler durduruluyor...")
        if self.flask_process:
            self.flask_process.terminate()
        if self.bridge_process:
            self.bridge_process.terminate()
        print("Sistem güvenle kapatıldı. İyi uçuşlar! ✈️")


if __name__ == "__main__":
    launcher = BackendLauncher()
    launcher.print_banner()
    launcher.start_services()
