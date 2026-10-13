# -*- coding: utf-8 -*-
"""KARAR MERKEZİ — İş ağırlığı sınıflandırma + modül yönlendirme.

İki görevi tek geçişte yapar (hızlı ve ucuz):
  1) Mesajı iş türüne göre AĞIR mı RUTİN mi olduğuna sınıflandırır
     (kod yazma/düzenleme, planlama, derin analiz → ağır).
  2) Hangi YETENEĞİN çağrılacağına karar verir (arama, dosya yazma, hafıza...).

Model JSON çıktısı veremezse kural tabanlı yedek sınıflandırıcı devreye girer;
böylece sistem her koşulda çalışmaya devam eder.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

AGIR_IPUCLARI = [
    "kod", "code", "yazılım", "programla", "hata", "debug", "refactor",
    "script", "python", "javascript", "sql", "tasarla", "mimari", "plan",
    "strateji", "analiz et", "hesapla", "algoritma", "sistem kur", "otomasyon",
    "test yaz", "veritabanı", "api",
]
RUTIN_IPUCLARI = [
    "merhaba", "selam", "nasılsın", "teşekkür", "günaydın", "iyi akşamlar",
    "kısaca", "ne demek", "hatırlıyor musun", "hava", "saat",
]


class SiniflandiriciYedek:
    """LLM'e ulaşamazsak veya bozuk JSON dönerse çalışan kuralcı."""

    def agir_mi(self, metin: str) -> float:
        t = metin.lower()
        agir = sum(1 for k in AGIR_IPUCLARI if k in t)
        rutin = sum(1 for k in RUTIN_IPUCLARI if k in t)
        uzunluk_puani = min(len(t) / 400.0, 1.0) * 0.5
        kod_bolmesi = 1.0 if ("```" in t or "\n" in metin and len(metin) > 300) else 0.0
        puan = min(1.0, 0.35 * agir + uzunluk_puani + kod_bolmesi * 0.5 - 0.3 * rutin)
        return round(max(0.0, puan), 2)

    def gorev_tahmini(self, metin: str) -> str:
        t = metin.lower()
        if any(k in t for k in ["ara", "bul", "güncel", "haber", "internet", "web"]):
            return "arama"
        if any(k in t for k in ["dosyaya yaz", "kaydet dosyaya", "not al", "yazdır"]):
            return "dosya_yazma"
        if any(k in t for k in ["hatırla", "geçmiş", "önceki", "ne yapmıştık"]):
            return "hafiza_ara"
        return "sohbet"


SINIF_SISTEM = """Sen bir görev dağıtım merkezisin. Kullanıcı mesajını analiz et ve
SADECE geçerli bir JSON nesnesi döndür, başka hiçbir şey yazma. Şema:
{
 "agirlik": 0.0-1.0,          # 1.0 = çok ağır iş (kod/planlama/derin analiz)
 "tur": "sohbet|kod|plan|analiz|arama|dosya|hatirlama|diger",
 "modul": "yok|arama|dosya_yazma|hafiza_ara",
 "modul_girdisi": "seçili modüle gönderilecek temiz girdi ya da boş string",
 "gerekce": "tek cümle Türkçe"
}
Kurallar:
- Sıradan sohbet/selamlaşma/bilgi sorma → agirlik <= 0.3, tur=sohbet, modul=yok.
- Kod yazma/düzeltme/tasarım, çok adımlı plan, derin analiz → agirlik >= 0.7.
- Güncel/dış dünya bilgisi gerekiyorsa (hava, haber, fiyat, son gelişme)
  modul=arama yap ve aranacak sorguyu modul_girdisi'ne yaz.
- Dosyaya içerik yazma/kaydetme istenirse modul=dosya_yazma.
- Geçmiş sohbet referansı istenirse modul=hafiza_ara.
Şimdi analiz et:"""


class KararMerkezi:
    def __init__(self, ollama, modul_sozlugu_getiricisi):
        self.ollama = ollama
        self._moduller = modul_sozlugu_getiricisi  # callable -> dict kod->sozlesme
        self.yedek = SiniflandiriciYedek()

    # ---------- dış arayüz ----------
    def karar_ver(self, metin: str, oturum: str = "") -> Dict[str, object]:
        ayar_modul = self._model_sec()
        sonuc: Optional[dict] = None
        kaynak = "kural"
        model = ayar_modul.get("siniflandirma_modeli") or ayar_modul.get("rutin_model")
        if model and self.ollama and self.ollama.canli_mi():
            try:
                ham = self.ollama.uretim(
                    model, [{"role": "user", "content": metin[:4000]}],
                    sistem=SINIF_SISTEM, sıcaklik=0.0, zaman_asimi=60)
                sonuc = self._json_kaziham(ham)
                if sonuc:
                    kaynak = "llm"
            except Exception:
                sonuc = None
        if sonuc is None:
            sonuc = {
                "agirlik": self.yedek.agir_mi(metin),
                "tur": "sohbet",
                "modul": ("yok" if self.yedek.gorev_tahmini(metin) == "sohbet"
                          else self.yedek.gorev_tahmini(metin)),
                "modul_girdisi": metin,
                "gerekce": "Kural tabanlı yedek sınıflandırıcı kullanıldı.",
            }
        sonuc["kaynak"] = kaynak
        sonuc.setdefault("modul", "yok")
        sonuc.setdefault("modul_girdisi", metin)
        sonuc.setdefault("agirlik", self.yedek.agir_mi(metin))
        sonuc["model_secimi"] = self.model_sec(sfloat(sonuc["agirlik"]), ayar_modul)
        return sonuc

    def _model_sec(self) -> Dict[str, str]:
        from cekirdek import yapilandirma
        return yapilandirma.yukle()["modeller"]

    @staticmethod
    def model_sec(agirlik: float, modeller: Dict[str, str]) -> str:
        esik = float(modeller.get("guc_orani", 0.55))
        agir = modeller.get("agir_model") or modeller.get("rutin_model")
        rutin = modeller.get("rutin_model") or agir
        return agir if agirlik >= esik else rutin

    @staticmethod
    def _json_kaziham(metin: str) -> Optional[dict]:
        m = re.search(r"\{.*\}", metin, flags=re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except Exception:
            return None
        if "agirlik" not in d:
            return None
        d["agirlik"] = float(d.get("agirlik", 0))
        d["modul"] = str(d.get("modul", "yok")).strip().lower()
        if d["modul"] not in ("yok", "hafiza_ara"):
            # gerçekten kurulu bir yetenek mi?
            mevcut = KararMerkezi._mevcut_kodlar()
            if d["modul"] not in mevcut:
                d["modul"] = "yok"
        return d

    @staticmethod
    def _mevcut_kodlar() -> List[str]:
        from cekirdek.modul_iskeleti import TEKIL
        return list(TEKIL.sozluk.keys())


def sfloat(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0
