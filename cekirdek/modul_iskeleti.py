# -*- coding: utf-8 -*-
"""MODÜL KALBI — Tak/Sök altyapısı.

İki modül türü vardır:
  • ORGAN   → sürekli aktif, arka planda döngüsü olan yeti (gözlem, hafıza...),
              `organlar/` klasöründe durur, `baslat()/dur()` metodları olur.
  • YETENEK → sadece gerektiğinde karar merkezi tarafından çağrılır,
              işi bitince serbest bırakılır, `yetenekler/` klasöründe durur.

Her modül bir `modul_bilgisi.py` dosyası taşır (anahtar=sabit sözlük).
Sistem açılışta ve "tara" çağrısında klasörleri tarar; yeni atılan klasör
otomatik görünür, silinen klasör otomatik sökülmüş sayılır.

Modül sözleşmesi (sohbet üzerinden çağırmak için):
    sozlesme = {
        "ad": ..., "tur": "organ"|"yetenek", "aciklama": ...,
        "gorev_anahtarlari": [...],     # kaba eşleştirme
        "cagri_ornekleri": [...],       # LLM'e örnek olarak gösterilir
        "calistir": fonksiyon,          # (metin, **saglamalar) -> str | dict
    }
"""
from __future__ import annotations

import importlib.util
import os
import threading
from typing import Dict, List, Optional

from . import yapilandirma

TUR_ORGAN = "organ"
TUR_YETENEK = "yetenek"
TUR_NODE = "node"      # nodeller/ klasöründeki takılabilir yetenek paketi

# tur → ayar sözlüğü anahtarı
_AYAR_ANAHTARI = {TUR_ORGAN: "organlar", TUR_YETENEK: "yetenekler",
                  TUR_NODE: "nodeller"}


def _ayar_anahtari(tur: str) -> str:
    return _AYAR_ANAHTARI.get(tur, "yetenekler")


class ModulYukleyici:
    def __init__(self):
        self._moduller: Dict[str, dict] = {}
        self._organ_calisan: set = set()
        self._kilit = threading.RLock()

    # ---------- tarama / kurulum ----------
    def _klasoru_tara(self, yol: str, tur: str) -> List[dict]:
        bulunan = []
        if not os.path.isdir(yol):
            return bulunan
        for isim in sorted(os.listdir(yol)):
            klasor = os.path.join(yol, isim)
            # Node arşiv alt klasörleri (kabul/sokulen/indirilen) MODÜL DEĞİLDİR:
            # nodeller/kabul gibi içlerinde modül klasörü barındıran dizinler
            # taranırken kendileri kayda geçmez; ancak nodeller/<kod>/ düz
            # node'ları yine de bulunur (kabul/sokulen adlı node olmaz).
            if tur == "node" and isim in ("kabul", "sokulen", "indirilen"):
                continue
            bilgi_dosya = os.path.join(klasor, "modul_bilgisi.py")
            ana_dosya = os.path.join(klasor, "modul.py")
            if os.path.isdir(klasor) and os.path.exists(bilgi_dosya):
                bulunan.append({"kod": isim, "tur": tur, "yol": klasor,
                                "bilgi_dosya": bilgi_dosya, "ana_dosya": ana_dosya})
        return bulunan

    def tara(self, yeniden: bool = False) -> List[dict]:
        """Diskteki tüm modülleri bulur, import eder, kayıt listesini döndürür.

        yeniden=True → önce kayıtlar temizlenir (SÖK/GESTALT işlemi):
        diskten düşen modül sozluk'ten de silinir; karar merkezi artık onu
        seçemez, organ ise durdurulmuş sayılır.
        """
        with self._kilit:
            if yeniden:
                for kod in [k for k, s in self._moduller.items()
                            if s.get("tur") == TUR_ORGAN]:
                    pass  # organlar etkinlik_ayarla ile zaten durdurulur
                self._moduller.clear()
                self._organ_calisan &= set()  # diskte olmayan kalmaz
            kayitlar = []
            adaylar = (self._klasoru_tara(yapilandirma.ORGAN_DIZIN, TUR_ORGAN)
                       + self._klasoru_tara(yapilandirma.YETENEK_DIZIN, TUR_YETENEK)
                       + self._klasoru_tara(yapilandirma.NODE_DIZIN, TUR_NODE))
            for a in adaylar:
                hata = None
                try:
                    sozlesme = self._sozlesme_yukle(a)
                except Exception as e:
                    sozlesme, hata = None, f"{type(e).__name__}: {e}"
                kayit = {
                    "kod": a["kod"],
                    "tur": a["tur"],
                    "ad": (sozlesme or {}).get("ad", a["kod"]),
                    "aciklama": (sozlesme or {}).get("aciklama", ""),
                    "surum": (sozlesme or {}).get("surum", "?"),
                    "gorev_anahtarlari": (sozlesme or {}).get("gorev_anahtarlari", []),
                    "hata": hata,
                    "etkin": False,
                }
                if sozlesme:
                    self._moduller[a["kod"]] = sozlesme
                kayitlar.append(kayit)

            ayarlar = yapilandirma.yukle()
            for k in kayitlar:
                havuz = ayarlar.get(_ayar_anahtari(k["tur"]), {})
                # tanınmayan yeni modül varsayılan olarak KURULU+AKTİF kabul edilir
                k["etkin"] = bool(havuz.get(k["kod"], True))
                s = self._moduller.get(k["kod"])
                if s:
                    s["etkin"] = k["etkin"]
            # arka planda çalışan ama diskten düşmüş organları durdur
            for kod in list(self._organ_calisan):
                if kod not in self._moduller:
                    self._organ_calisan.discard(kod)
            self._son_kayitlar = kayitlar
            return kayitlar

    def _sozlesme_yukle(self, aday: dict) -> Optional[dict]:
        spec = importlib.util.spec_from_file_location(
            f"modul_{aday['kod']}", aday["ana_dosya"])
        if spec is None or spec.loader is None:
            raise RuntimeError("modul.py yüklenemedi")
        mod = importlib.util.module_from_spec(spec)
        # Modül kendi klasörünü sys.path'e ekleyebilsin diye kaydet
        # (arastirmaci gibi çok dosyalı modüller için; sökme sırasında
        #  klasör silinince bu yol geçersiz kalır ama zararsızdır)
        import os as _os
        _klasor = _os.path.dirname(aday["ana_dosya"])
        if _klasor not in __import__("sys").path:
            __import__("sys").path.insert(0, _klasor)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "sozlesme"):
            raise RuntimeError("modülde 'sozlesme' sözlüğü yok")
        s = dict(mod.sozlesme)
        s.setdefault("kod", aday["kod"])
        s.setdefault("tur", aday["tur"])
        return s

    # ---------- organ yaşam döngüsü ----------
    def organlari_baslat(self) -> List[dict]:
        """Etkin organların baslat()'ını çağırır.

        Not: Hafıza organının asıl nesnesi çekirdekte (GorevGonderici) yaşar;
        modülün kendi baslat() metodu o nesneye bağlanmıştır. Modül dosyasını
        ikinci kez import edip sahte çift nesne oluşturmamak için tekil çekirdek
        örneği buradan enjekte edilir.
        """
        try:
            from cekirdek.gonderci import GONDERCI_BAGI
            if GONDERCI_BAGI.get("hafiza") is not None:
                self._moduller.setdefault("hafiza", {})["baslat"] =                     GONDERCI_BAGI["hafiza"].baslat
                self._moduller["hafiza"]["dur"] = GONDERCI_BAGI["hafiza"].dur
                self._moduller["hafiza"]["calistir"] = GONDERCI_BAGI["hafiza"].calistir
                self._moduller["hafiza"].setdefault("tur", "organ")
                self._moduller["hafiza"].setdefault("ad", "Hafıza (Hipokampüs)")
                self._moduller["hafiza"].setdefault("kod", "hafiza")
        except Exception:
            pass
        sonuc = []
        for kod, s in list(self._moduller.items()):
            if s.get("tur") != TUR_ORGAN or kod in self._organ_calisan:
                continue
            if not s.get("etkin", True):
                continue
            try:
                dur_durdur = s.get("baslat")
                if callable(dur_durdur):
                    dur_durdur()
                self._organ_calisan.add(kod)
                sonuc.append({"kod": kod, "durum": "çalışıyor"})
            except Exception as e:
                sonuc.append({"kod": kod, "durum": f"hata: {e}"})
        return sonuc

    def organlari_durdur(self):
        for kod in list(self._organ_calisan):
            s = self._moduller.get(kod, {})
            try:
                if callable(s.get("dur")):
                    s["dur"]()
            except Exception:
                pass
            self._organ_calisan.discard(kod)

    def etkinlik_ayarla(self, kod: str, tur: str, acik: bool) -> dict:
        alan = _ayar_anahtari(tur)
        yapilandirma.guncelle({alan: {kod: bool(acik)}})
        s = self._moduller.get(kod)
        if s:
            s["etkin"] = bool(acik)
        if tur == TUR_ORGAN:
            if acik and s and kod not in self._organ_calisan:
                self.organlari_baslat()
            elif not acik and kod in self._organ_calisan:
                try:
                    if s and callable(s.get("dur")):
                        s["dur"]()
                finally:
                    self._organ_calisan.discard(kod)
        return {"kod": kod, "tur": tur, "etkin": bool(acik)}

    # ---------- çağırma ----------
    def yetenek_getir(self, kod: str) -> Optional[dict]:
        s = self._moduller.get(kod)
        if s and s.get("tur") == TUR_YETENEK and s.get("etkin", True):
            return s
        return None

    def organ_getir(self, kod: str) -> Optional[dict]:
        s = self._moduller.get(kod)
        if s and s.get("tur") == TUR_ORGAN and s.get("etkin", True):
            return s
        return None

    def modulu_calistir(self, kod: str, metin: str, **saglama) -> dict:
        s = self._moduller.get(kod)
        if not s:
            return {"basarili": False, "yanit": "", "hata": f"'{kod}' modülü bulunamadı."}
        try:
            yanit = s["calistir"](metin, **saglama)
            if isinstance(yanit, dict):
                return {"basarili": True, **yanit}
            return {"basarili": True, "yanit": str(yanit)}
        except Exception as e:
            return {"basarili": False, "yanit": "", "hata": f"{type(e).__name__}: {e}"}

    @property
    def sozluk(self) -> Dict[str, dict]:
        return self._moduller


TEKIL = ModulYukleyici()
