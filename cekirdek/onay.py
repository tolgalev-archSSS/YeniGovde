# -*- coding: utf-8 -*-
"""İZİN KAPICISI — Sistem geneli onay / izin altyapısı (çekirdek hizmet).

Modüller (ör. EL yeteneği) tehlikeli bir eylem yapmak istediğinde buradan
geçer. Akış (ONAY_AKISI_TASARIM.md):

  kırmızı çizgi mi?  → otomatik RET (kuyruğa bile girmez)
  yetkili bölge dışı mı? → otomatik RET
  serbest sınıf mı? (okuma / program açma) → otomatik ONAY
  izin defterinde kayıt var mı? → ona göre ONAY/RET
  hiçbiri değilse → PANELDE ONAY KARTI üret, kullanıcı seçene kadar bekle

Kullanıcı kartındaki seçenekler:
  "tek"      → yalnız bu sefer
  "oturum"   → bu oturum (sistem açık kaldığı süre) boyunca aynı tür+alan serbest
  "kalici"   → kalıcı izin (ayarlar/onay_defteri.json'a yazılır)
  "ret"      → reddet

Zaman aşımı: ZAMAN_ASIMI sn içinde yanıt gelmezse eylem REDDEDİLİR.
Panel yenilenirse bekleyen kartlar GET /api/onaylar ile geri gelir.

Bu modül çekirdektedir; hiçbir eklentiye bağımlılığı yoktur. Bir yetenek
onay sormak İSTEMEZSE bu katmanı hiç kullanmaz — tak/sök mimarisi bozulmaz.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Dict, List, Optional

from cekirdek import yapilandirma

BEKLEME_SURESI_SN = 300          # onay kartı 5 dk yanıtsız kalrsa reddedilir
TEMIZLIK_ARALIGI_SN = 60

# Onay sorulmadan geçen hafif eylemler
SERBEST_EYLEMLER = {"dosya_oku", "klasor_listele", "program_ac", "program_listele"}

# Dış dünyaya açılan eylemler (arama modülleri) — kullanıcı "serbest" yapmazsa sorulur
DIS_DUNYA_EYLEMLERI = {"web_ara", "sayfa_oku", "kurul_ara", "detayli_ara"}


def dis_dunya_serbest_mi() -> bool:
    """ayarlar/arama.onay_serbest == True ise dış dünya işlemleri onaysız geçer."""
    try:
        return bool(yapilandirma.yukle().get("arama", {}).get("onay_serbest"))
    except Exception:
        return False

# Silinemeyecek / değiştirilemeyecek kritik yol parçaları (küçük harf)
KIRMIZI_CIZGI_PARCALARI = [
    "c:/windows", "c:\\windows", "/etc", "/boot", "/sys", "/proc", "/usr",
    "windows\\system32", "$recycle.bin", "onegetms", "winnt",
]


def _izin_dosyasi() -> str:
    return os.path.join(yapilandirma.AYAR_DIZIN, "onay_defteri.json")


def _gunluk_dosyasi() -> str:
    return os.path.join(yapilandirma.LOG_DIZIN, "el_gunlugu.jsonl")


def yolu_kirmizi_cizgi_mi(yol: str) -> bool:
    t = os.path.abspath(yol).replace("\\", "/").lower()
    for p in KIRMIZI_CIZGI_PARCALARI:
        if p.replace("\\", "/") in t:
            return True
    return False


class IzinKapicisi:
    """Tekil onay motoru. iplik-güvenlidir."""

    def __init__(self):
        self._kilit = threading.RLock()
        self._bekleyen: Dict[str, dict] = {}       # kimlik -> kart kaydı
        self._olay: Dict[str, threading.Event] = {}
        self._oturum_izinleri: set = set()          # sistem açıkken geçerli
        self._defter: List[dict] = self._defter_oku()
        self._temizlik_zamanla()

    # ---------- kalıcı defter ----------
    def _defter_oku(self) -> List[dict]:
        try:
            with open(_izin_dosyasi(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _defter_yaz(self):
        os.makedirs(yapilandirma.AYAR_DIZIN, exist_ok=True)
        tmp = _izin_dosyasi() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._defter, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _izin_dosyasi())

    @staticmethod
    def _anahtar(eylem: str, alan: str) -> str:
        return f"{eylem}|{alan or '*'}"

    def defterdeki_izinler(self) -> List[dict]:
        with self._kilit:
            return list(self._defter)

    def oturum_izinleri(self) -> List[str]:
        with self._kilit:
            return sorted(self._oturum_izinleri)

    def izin_iptal(self, anahtar: str) -> bool:
        """Kalıcı izni siler. anahtar boşsa TÜMÜ silinir."""
        with self._kilit:
            once = len(self._defter)
            self._defter = [d for d in self._defter
                            if not (anahtar in ("", "*", None) or d["anahtar"] == anahtar)]
            self._defter_yaz()
            return len(self._defter) != once

    # ---------- günlük ----------
    def gunluga_yaz(self, kayit: dict):
        try:
            os.makedirs(yapilandirma.LOG_DIZIN, exist_ok=True)
            kayit.setdefault("zaman", time.strftime("%Y-%m-%d %H:%M:%S"))
            with open(_gunluk_dosyasi(), "a", encoding="utf-8") as f:
                f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ---------- karar ağacı ----------
    def denetle(self, eylem: str, hedef: str, aciklama: str = "",
                alan: str = "") -> dict:
        """Eyleme izin var mı?  {onayli: bool, kaynak, neden, kart?}"""
        with self._kilit:
            # 1) kırmızı çizgi
            if yollar_kirmizi_cizgi_mi(hedef):
                self.gunluga_yaz({"eylem": eylem, "hedef": hedef,
                                  "sonuc": "ENGEL", "neden": "kırmızı çizgi"})
                return {"onayli": False, "kaynak": "kirmizi_cizgi",
                        "neden": f"'{hedef}' korumalı bir sistem bölgesi; "
                                 "bu eylem her zaman yasaktır."}
            # 2) serbest sınıf
            if eylem in SERBEST_EYLEMLER:
                return {"onayli": True, "kaynak": "serbest_sinif", "neden": ""}
            # 2b) dış dünya eylemleri: kullanıcı ayarlarda serbest bıraktıysa sorulmaz
            if eylem in DIS_DUNYA_EYLEMLERI and dis_dunya_serbest_mi():
                return {"onayli": True, "kaynak": "ayar_serbest", "neden": ""}
            # 3) izin defteri (kalıcı / oturum)
            anahtar = self._anahtar(eylem, alan)
            tam_yol_anahtari = self._anahtar(eylem, "*")
            if any(d["anahtar"] in (anahtar, tam_yol_anahtari) for d in self._defter):
                return {"onayli": True, "kaynak": "kalici_izin", "neden": ""}
            if anahtar in self._oturum_izinleri or tam_yol_anahtari in self._oturum_izinleri:
                return {"onayli": True, "kaynak": "oturum_izni", "neden": ""}
            # 4) onay kartı üret ve sonucu bekle
            kart = self._kart_uret(eylem, hedef, aciklama, alan)
        kimlik = kart["kimlik"]
        olay = self._olay[kimlik]
        tamam = olay.wait(timeout=BEKLEME_SURESI_SN)
        with self._kilit:
            kayit = self._bekleyen.pop(kimlik, {})
            self._olay.pop(kimlik, None)
        secim = kayit.get("secim") if tamam else None
        self.gunluga_yaz({"eylem": eylem, "hedef": hedef, "kimlik": kimlik,
                          "sonuc": secim or "ZAMAN_ASIMI"})
        if secim in ("tek", "oturum", "kalici"):
            if secim == "oturum":
                self._oturum_izinleri.add(self._anahtar(eylem, alan))
            elif secim == "kalici":
                self._defter.append({
                    "anahtar": self._anahtar(eylem, alan),
                    "eylem": eylem, "alan": alan or "*",
                    "eklendi": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "ilk_hedef": hedef})
                self._defter_yaz()
            return {"onayli": True, "kaynak": f"kullanici_onayi:{secim}", "neden": ""}
        if secim == "ret":
            return {"onayli": False, "kaynak": "kullanici_reddi",
                    "neden": "Kullanıcı bu işlemi reddetti."}
        return {"onayli": False, "kaynak": "zaman_asimi",
                "neden": f"Onay {BEKLEME_SURESI_SN} saniye içinde verilmedi; "
                         "işlem güvenliği için iptal edildi."}

    # ---------- kart yaşam döngüsü ----------
    def _kart_uret(self, eylem: str, hedef: str, aciklama: str, alan: str) -> dict:
        kimlik = uuid.uuid4().hex[:8]
        kart = {
            "kimlik": kimlik,
            "eylem": eylem,
            "hedef": os.path.abspath(hedef) if hedef else "",
            "aciklama": aciklama,
            "alan": alan or "*",
            "durum": "bekliyor",
            "istek_zamani": time.strftime("%H:%M:%S"),
        }
        self._bekleyen[kimlik] = kart
        self._olay[kimlik] = threading.Event()
        return kart

    def bekleyenleri_getir(self) -> List[dict]:
        with self._kilit:
            return [dict(k) for k in self._bekleyen.values()
                    if k["durum"] == "bekliyor"]

    def yanit_ver(self, kimlik: str, secim: str) -> dict:
        """Panel butonlarından gelir: tek|oturum|kalici|ret"""
        with self._kilit:
            kart = self._bekleyen.get(kimlik)
            if not kart or kart["durum"] != "bekliyor":
                return {"basarili": False, "neden": "Kart bulunamadı (süresi dolmuş olabilir)."}
            if secim not in ("tek", "oturum", "kalici", "ret"):
                return {"basarili": False, "neden": f"Geçersiz seçim: {secim}"}
            kart["secim"] = secim
            kart["durum"] = "karar_verildi"
            olay = self._olay.get(kimlik)
        if olay:
            olay.set()
        return {"basarili": True, "kart": kart}

    # ---------- zaman aşımı temizliği ----------
    def _temizlik_zamanla(self):
        def dongu():
            while True:
                time.sleep(TEMIZLIK_ARALIGI_SN)
                su = time.time()
                with self._kilit:
                    for kimlik, kart in list(self._bekleyen.items()):
                        t0 = time.strptime(kart["istek_zamani"], "%H:%M:%S")
                        gecen = su - (t0.tm_hour * 3600 + t0.tm_min * 60 + t0.tm_sec)
                        if kart["durum"] == "bekliyor" and gecen > BEKLEME_SURESI_SN:
                            kart["durum"] = "suresi_doldu"
                            olay = self._olay.get(kimlik)
                            if olay:
                                olay.set()
        threading.Thread(target=dongu, daemon=True, name="kapici-temizlik").start()


def yollar_kirmizi_cizgi_mi(*yollar: str) -> bool:
    return any(yolu_kirmizi_cizgi_mi(y) for y in yollar if y)


TEKIL_KAPICI = IzinKapicisi()
