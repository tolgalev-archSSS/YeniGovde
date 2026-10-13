# -*- coding: utf-8 -*-
"""EL — DOSYA VE PROGRAM EYLEMLERİ (yeteneğin kasları).

Her eylem TEK BİR sözdizimiyle çağrılır ve daima sözlük döndürür:
    {"basarili": bool, "yanit": str, ...ek alanlar}

Güvenlik ilkeleri (ONAY_AKISI_TASARIM.md):
  • Okuma ve program açma serbest; yazma/silme/taşıma/tamamen silme → kapıcı onayı.
  • Silme asla kalıcı değildir: çöp kutusuna gönderilir (send2trash),
    Windows'ta geri alınabilir. Çöp kutusu yoksa system_komutu'na devredilir.
  • Yazmadan önce hedef varsa gölge kopya alınır (veri/el_yedek/).
  • Hedef yol burada gerçek yola çevrilir; kullanıcı/kural yolu elle giremez,
    panelde daima EL'in çözümlediği mutlak yol gösterilir.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from cekirdek import yapilandirma
from cekirdek.onay import TEKIL_KAPICI

KOK_DIZIN = yapilandirma.KOK_DIZIN
YEDEK_DIZIN = os.path.join(yapilandirma.VERI_DIZIN, "el_yedek")

try:
    from send2trash import send2trash as cop_kutusu_gonder
except Exception:
    cop_kutusu_gonder = None


def _alan(hedef: str) -> str:
    """Onay anahtarının 'alan' kısmı: sürücü veya home üstü tek klasör."""
    t = os.path.abspath(hedef)
    parcalar = t.replace("\\", "/").split("/")
    govde = [p for p in parcalar if p]
    return "/" + govde[0] if govde else "*"


def _gercek_yol(yol: str) -> str:
    """Ham yolu (ev dizini ~, göreli vb.) mutlaklaştırır."""
    genis = os.path.expanduser(os.path.expandvars((yol or "").strip().strip('"')))
    if not os.path.isabs(genis):
        genis = os.path.join(os.getcwd(), genis)
    return os.path.normpath(genis)


def _golge_kopya(hedef: str) -> str:
    """Yazma/silme öncesi hedefin kopyasını yedek klasörüne alır."""
    if not os.path.isfile(hedef):
        return ""
    os.makedirs(YEDEK_DIZIN, exist_ok=True)
    ad = os.path.basename(hedef)
    zaman = __import__("time").strftime("%Y%m%d_%H%M%S")
    kopya = os.path.join(YEDEK_DIZIN, f"{zaman}_{ad}")
    try:
        shutil.copy2(hedef, kopya)
        return kopya
    except Exception:
        return ""


def _izin_al(eylem: str, hedef: str, aciklama: str) -> dict:
    """Kapıcıyı GERÇEKTEN çağırır (kart açar/bekletir).

    EL'in ortak girişi (modul.calistir) denetimi zaten tek noktada yaptığı
    için buradan gelen istekler 'çoktan-onaylı' sayılır; eylem işlevleri bu
    yüzden yalnızca izin KAYNAĞINI etiket olarak taşır. Başka bir modül bu
    işlevleri doğrudan kullanmak isterse kapıcıyı kendisi çağırmalıdır.
    """
    return {"onayli": True, "kaynak": "el_giris_denetledi", "neden": ""}


# ============================ DOSYA EYLEMLERİ ============================
# NOT: Onay denetimi tek noktada (yetenekler/el/modul.py → calistir) yapılır;
# buradaki işlevler kapıcıyı yeniden çağırmaz (çift onay kartı açılmasın).

def dosya_oku(hedef: str, **s) -> dict:
    yol = _gercek_yol(hedef)
    if not os.path.isfile(yol):
        return {"basarili": False, "yanit": f"Dosya bulunamadı: {yol}"}
    try:
        with open(yol, "r", encoding="utf-8", errors="replace") as f:
            icerik = f.read(200_000)   # tek seferde en fazla 200 KB
        return {"basarili": True, "yanit": icerik, "yol": yol,
                "karakter": len(icerik)}
    except Exception as e:
        return {"basarili": False, "yanit": f"Okuma hatası: {e}"}


def klasor_listele(hedef: str, **s) -> dict:
    yol = _gercek_yol(hedef)
    if not os.path.isdir(yol):
        return {"basarili": False, "yanit": f"Klasör bulunamadı: {yol}"}
    try:
        girisler = []
        for isim in sorted(os.listdir(yol))[:400]:
            tam = os.path.join(yol, isim)
            tur = "D" if os.path.isdir(tam) else "d"
            boyut = os.path.getsize(tam) if tur == "d" else 0
            girisler.append(f"[{tur}] {isim}" + (f" ({boyut}B)" if boyut else ""))
        return {"basarili": True, "yanit": "\n".join(girisler) or "(boş)", "yol": yol}
    except Exception as e:
        return {"basarili": False, "yanit": f"Listeleme hatası: {e}"}


def dosya_yaz(hedef: str, icerik: str = "", ekleyerek: bool = False,
              aciklama: str = "", **s) -> dict:
    if not icerik:
        return {"basarili": False, "yanit": "Yazılacak içerik boş."}
    yol = _gercek_yol(hedef)
    izin = _izin_al("dosya_yaz", yol, aciklama or f"{os.path.basename(yol)} dosyasına yazılıyor")
    if not izin["onayli"]:
        return {"basarili": False, "yanit": f"İzin verilmedi ({izin['kaynak']}). {izin['neden']}"}
    yedek = _golge_kopya(yol)
    try:
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "a" if ekleyerek else "w", encoding="utf-8") as f:
            f.write(icerik)
        return {"basarili": True,
                "yanit": f"{'Eklendi' if ekleyerek else 'Yazıldı'} → {yol} "
                         f"({len(icerik)} karakter)" + (f" · yedek: {yedek}" if yedek else ""),
                "yol": yol, "yedek": yedek, "onay": izin["kaynak"]}
    except Exception as e:
        return {"basarili": False, "yanit": f"Yazma hatası: {e}"}


def dosya_duzelt(hedef: str, eski: str = "", yeni: str = "",
                 aciklama: str = "", **s) -> dict:
    """Dosya içinde metin değiştirme — her zaman ONAYA gider."""
    yol = _gercek_yol(hedef)
    if not os.path.isfile(yol):
        return {"basarili": False, "yanit": f"Dosya bulunamadı: {yol}"}
    if not eski:
        return {"basarili": False, "yanit": "'eski' metni belirtilmedi."}
    izin = _izin_al("dosya_duzelt", yol,
                    aciklama or f"'{eski[:60]}' → '{yeni[:60]}' olarak değiştirilecek")
    if not izin["onayli"]:
        return {"basarili": False, "yanit": f"İzin verilmedi ({izin['kaynak']}). {izin['neden']}"}
    yedek = _golge_kopya(yol)
    try:
        with open(yol, "r", encoding="utf-8", errors="replace") as f:
            icerik = f.read()
        adet = icerik.count(eski)
        if adet == 0:
            return {"basarili": False, "yanit": f"Aranan metin bulunamadı: {eski[:80]}"}
        icerik = icerik.replace(eski, yeni)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)
        return {"basarili": True,
                "yanit": f"{adet} yerde değiştirildi → {yol}" + (f" · yedek: {yedek}" if yedek else ""),
                "yol": yol, "degisim_sayisi": adet, "yedek": yedek,
                "onay": izin["kaynak"]}
    except Exception as e:
        return {"basarili": False, "yanit": f"Düzeltme hatası: {e}"}


def dosya_sil(hedef: str, aciklama: str = "", **s) -> dict:
    """Çöp kutusuna gönderir — GERİ ALINABİLİR. Onaya gider."""
    yol = _gercek_yol(hedef)
    if not os.path.exists(yol):
        return {"basarili": False, "yanit": f"Bulunamadı: {yol}"}
    izin = _izin_al("dosya_sil", yol, aciklama or f"{os.path.basename(yol)} çöp kutusuna gönderilecek")
    if not izin["onayli"]:
        return {"basarili": False, "yanit": f"İzin verilmedi ({izin['kaynak']}). {izin['neden']}"}
    yedek = _golge_kopya(yol)
    try:
        if cop_kutusu_gonder:
            cop_kutusu_gonder(yol)
            nasil = "çöp kutusuna gönderildi (geri alınabilir)"
        elif sys.platform.startswith("win"):
            subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 'Add-Type -AssemblyName Microsoft.VisualBasic;'
                 '[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('
                 f'"{yol}","OnlyErrorDialogs","SendToRecycleBin")'], check=True)
            nasil = "Windows çöp kutusuna gönderildi"
        else:
            carp = os.path.join(YEDEK_DIZIN, "silinenler")
            os.makedirs(carp, exist_ok=True)
            shutil.move(yol, os.path.join(carp, os.path.basename(yol)))
            nasil = f"{carp} altına taşındı (geri alınabilir)"
        return {"basarili": True, "yanit": f"{yol} → {nasil}",
                "yol": yol, "yedek": yedek, "onay": izin["kaynak"]}
    except Exception as e:
        return {"basarili": False, "yanit": f"Silme hatası: {e}"}


def dosya_tasi(kaynak: str, hedef: str, aciklama: str = "", **s) -> dict:
    kaynak_yol, hedef_yol = _gercek_yol(kaynak), _gercek_yol(hedef)
    if not os.path.exists(kaynak_yol):
        return {"basarili": False, "yanit": f"Kaynak yok: {kaynak_yol}"}
    izin = _izin_al("dosya_tasi", kaynak_yol,
                    aciklama or f"{os.path.basename(kaynak_yol)} → {hedef_yol}")
    if not izin["onayli"]:
        return {"basarili": False, "yanit": f"İzin verilmedi ({izin['kaynak']}). {izin['neden']}"}
    try:
        os.makedirs(os.path.dirname(hedef_yol), exist_ok=True)
        shutil.move(kaynak_yol, hedef_yol)
        return {"basarili": True, "yanit": f"Taşındı: {kaynak_yol} → {hedef_yol}",
                "onay": izin["kaynak"]}
    except Exception as e:
        return {"basarili": False, "yanit": f"Taşıma hatası: {e}"}


def klasor_olustur(hedef: str, aciklama: str = "", **s) -> dict:
    yol = _gercek_yol(hedef)
    izin = _izin_al("klasor_olustur", yol, aciklama or f"Yeni klasör: {yol}")
    if not izin["onayli"]:
        return {"basarili": False, "yanit": f"İzin verilmedi ({izin['kaynak']}). {izin['neden']}"}
    try:
        os.makedirs(yol, exist_ok=True)
        return {"basarili": True, "yanit": f"Klasör hazır: {yol}", "onay": izin["kaynak"]}
    except Exception as e:
        return {"basarili": False, "yanit": f"Oluşturma hatası: {e}"}


# ============================ PROGRAM EYLEMLERİ ============================

def program_ac(hedef: str, girdi: str = "", **s) -> dict:
    """Program/belge başlatır (SERBEST sınıf). girdi → komut satırı argümanı."""
    hedef = (hedef or "").strip().strip('"')
    if not hedef:
        return {"basarili": False, "yanit": "Açılacak program/belge belirtilmedi."}
    try:
        if sys.platform.startswith("win"):
            komut = ["cmd", "/c", "start", "", hedef] + ([girdi] if girdi else [])
        elif sys.platform == "darwin":
            komut = ["open", hedef] + ([girdi] if girdi else [])
        else:
            komut = [hedef] + ([girdi] if girdi else [])
        subprocess.Popen(komut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"basarili": True, "yanit": f"Başlatıldı: {hedef} {girdi}".strip()}
    except Exception as e:
        return {"basarili": False, "yanit": f"Başlatma hatası: {e}"}


def program_listele(sorgu: str = "", **s) -> dict:
    try:
        import psutil
    except Exception:
        return {"basarili": False, "yanit": "psutil kurulu değil (pip install psutil)."}
    satirlar = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            ad = (p.info["name"] or "").lower()
            if not sorgu or sorgu.lower() in ad:
                satirlar.append(f"{p.info['pid']:>7}  {p.info['name']}")
        except Exception:
            continue
    return {"basarili": True, "yanit": "\n".join(satirlar[:120]) or "eşleşme yok",
            "sayi": len(satirlar)}


def program_kapat(hedef: str, aciklama: str = "", **s) -> dict:
    """Süreç adı veya PID ile kapatır — ONAYA gider."""
    try:
        import psutil
    except Exception:
        return {"basarili": False, "yanit": "psutil kurulu değil (pip install psutil)."}
    hedef = (hedef or "").strip().lower()
    izin = _izin_al("program_kapat", KOK_DIZIN,
                    aciklama or f"'{hedef}' adlı süreçler sonlandırılacak")
    if not izin["onayli"]:
        return {"basarili": False, "yanit": f"İzin verilmedi ({izin['kaynak']}). {izin['neden']}"}
    kapanan, atlanan = [], []
    pid_mi = hedef.isdigit()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            eslesme = (p.info["pid"] == int(hedef)) if pid_mi \
                else hedef in (p.info["name"] or "").lower()
            if not eslesme:
                continue
            if p.pid == os.getpid():
                atlanan.append("kendi sürecim (atlandı)")
                continue
            ad, soy = p.name().split(".")[0], psutil.Process(os.getpid()).name().split(".")[0]
            if ad == soy:
                atlanan.append(p.info["name"])
                continue
            p.terminate()
            kapanan.append(f"{p.info['name']}({p.info['pid']})")
        except Exception:
            continue
    mesaj = ("Sonlandırıldı: " + ", ".join(kapanan)) if kapanan else "eşleşen süreç yok"
    if atlanan:
        mesaj += " · korundu: " + ", ".join(atlanan)
    return {"basarili": bool(kapanan), "yanit": mesaj, "onay": izin["kaynak"]}


# ============================ ORTAK GİRİŞ NOKTASI ============================

_EYLEMLER = {
    "dosya_oku": dosya_oku,
    "klasor_listele": klasor_listele,
    "dosya_yaz": dosya_yaz,
    "dosya_duzelt": dosya_duzelt,
    "dosya_sil": dosya_sil,
    "dosya_tasi": dosya_tasi,
    "klasor_olustur": klasor_olustur,
    "program_ac": program_ac,
    "program_listele": program_listele,
    "program_kapat": program_kapat,
}

EYLEM_ETIKETLERI = {
    "dosya_oku": "Dosya Oku", "klasor_listele": "Klasör Listele",
    "dosya_yaz": "Dosyaya Yaz", "dosya_duzelt": "Metin Değiştir",
    "dosya_sil": "Çöp Kutusuna Gönder", "dosya_tasi": "Taşı",
    "klasor_olustur": "Klasör Oluştur", "program_ac": "Program Aç",
    "program_listele": "Süreçleri Listele", "program_kapat": "Program Kapat",
}


def eylem_calistir(ad: str, **parametre) -> dict:
    islev = _EYLEMLER.get(ad)
    if not islev:
        return {"basarili": False,
                "yanit": f"Bilinmeyen eylem '{ad}'. Geçerliler: "
                         + ", ".join(sorted(_EYLEMLER))}
    return islev(**parametre)
