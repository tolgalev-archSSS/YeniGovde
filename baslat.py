# -*- coding: utf-8 -*-
"""SİSTEM BAŞLATICI — Tek giriş noktası.

Çalıştırıldığında sırasıyla:
 1) Python sürümü ve bağımlılık kontrolü (Flask, requests) → eksikse otomatik `pip install`
 2) Gerekli klasörlerin oluşturulması / bozuk ayar onarımı
 3) Ollama kontrolü: değilse `ollama serve` arka planda başlatma denemesi
 4) Modül taraması (organlar/ + yetenekler/) ve organların başlatılması
 5) Model seçimlerinin doğrulanması (yüklü değilse temizlenir → arayüz yönlendirir)
 6) Flask sunucusunun başlatılması ve varsayılan tarayıcıda panelin açılması
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser

KOK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KOK)


def adim(no: int, metin: str):
    print(f"[{no}/6] {metin}", flush=True)


def kontrol_py():
    if sys.version_info < (3, 9):
        print("!! Python 3.9+ gerekli. Şu an:", sys.version.split()[0])
        sys.exit(1)
    adim(1, f"Python {sys.version.split()[0]} tamam.")


def kontrol_bagimliliklar():
    adim(2, "Bağımlılıklar kontrol ediliyor...")
    eksik = []
    for paket, mod in (("flask", "flask"), ("requests", "requests")):
        try:
            __import__(mod)
        except ImportError:
            eksik.append(paket)
    if eksik:
        print("     Eksik paketler kuruluyor:", ", ".join(eksik))
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", *eksik])
        if r.returncode != 0:
            print("     Kurulum başarısız! Elle kurun: pip install " + " ".join(eksik))
            input("Devam için Enter...")
    else:
        print("     Tüm bağımlılıklar tam.")


def kontrol_dizin_ve_ayar():
    adim(3, "Klasörler ve ayar dosyası hazırlanıyor...")
    from cekirdek import yapilandirma
    yapilandirma.gerekli_dizinler()
    yapilandirma.yukle()  # yoksa oluşturur, bozuksa onarır
    print("     Ayar dosyası: ayarlar/ayarlar.json")


def kontrol_ollama():
    adim(4, "Ollama kontrol ediliyor...")
    from cekirdek.ollama_kontrol import OllamaIstemcisi
    from cekirdek import yapilandirma
    adres = yapilandirma.yukle()["ollama"]["adres"]
    istemci = OllamaIstemcisi(adres)
    if istemci.canli_mi():
        print(f"     Ollama ÇALIŞIYOR (sürüm {istemci.surumu_al()}).")
        return True
    print("     Ollama kapalı görünüyor; 'ollama serve' başlatılmaya deneniyor...")
    try:
        CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(["ollama", "serve"], creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(10):
            time.sleep(1)
            if istemci.canli_mi():
                break
    except FileNotFoundError:
        pass
    if istemci.canli_mi():
        print("     Ollama başlatıldı.")
        return True
    print("     !! Ollama'ya ulaşılamadı. Kurulu mu? (https://ollama.com/download)")
    print("     !! Panel yine de açılacak; kurup başlattıktan sonra sayfayı yenilemeniz yeter.")
    return False


def kontrol_modeller():
    adim(5, "Modüller taranıyor ve model seçimleri doğrulanıyor...")
    from cekirdek import yapilandirma
    from cekirdek.modul_iskeleti import TEKIL
    kayitlar = TEKIL.tara()
    for k in kayitlar:
        durum = "HATALI: " + k["hata"] if k["hata"] else ("etkin" if k["etkin"] else "sökülmüş")
        print(f"     - [{k['tur']}] {k['ad']}  ({durum})")
    # seçili modeller artık yüklü değilse temizle → arayüz yeniden seçtirir
    from cekirdek.ollama_kontrol import OllamaIstemcisi
    istemci = OllamaIstemcisi(yapilandirma.yukle()["ollama"]["adres"])
    if istemci.canli_mi():
        yuku = {m["ad"] for m in istemci.modelleri_tara()}
        a = yapilandirma.yukle()["modeller"]
        guncelleme = {}
        for alan in ("rutin_model", "agir_model", "siniflandirma_modeli"):
            secim = a.get(alan, "")
            if secim and not any(secim == ad or secim.split(":")[0] == ad.split(":")[0]
                                 for ad in yuku):
                print(f"     ! '{secim}' ({alan}) artık yüklü değil, seçim temizleniyor.")
                guncelleme[alan] = ""
        if guncelleme:
            yapilandirma.guncelle({"modeller": guncelleme})
    return kayitlar


def sunucuyu_ac(ip_port=None):
    adim(6, "Üretim paneli başlatılıyor...")
    from cekirdek import yapilandirma
    from web.uygulama import app
    a = yapilandirma.yukle()["sunucu"]
    ip, port = a["ip"], int(a["port"])
    url = f"http://{ip}:{port}"
    if not os.environ.get("MLAO_PENCERE_YOK"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"\n     PANEL HAZIR  →  {url}")
    print("     Kapatmak için bu pencereyi CTRL+C ile durdurun.\n")
    app.run(host=ip, port=port, debug=False, threaded=True)


def main():
    print("=" * 58)
    print("   MODÜLER YEREL ZEKÂ SİSTEMİ — OTOMATİK BAŞLATICI")
    print("=" * 58)
    kontrol_py()
    kontrol_bagimliliklar()
    kontrol_dizin_ve_ayar()
    kontrol_ollama()
    kontrol_modeller()
    try:
        sunucuyu_ac()
    except KeyboardInterrupt:
        print("\nSistem kapatılıyor...")
    except Exception as e:
        print("\n!! Sunucu açılamadı:", e)
        print("   Port kullanımda olabilir; ayarlar/ayarlar.json içindeki")
        print("   sunucu.port değerini değiştirip tekrar deneyin.")
        if os.name == "nt":
            input("Enter...")


if __name__ == "__main__":
    main()
