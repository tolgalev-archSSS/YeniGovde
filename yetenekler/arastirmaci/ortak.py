# -*- coding: utf-8 -*-
"""ORTAK — Arama Kurulu birimlerinin ortak veri sözleşmesi ve yardımcılar.

Her birim `ara(gorev) -> List[Sonuc]` üretir. Sonuc alanları (zorunlu olanlar
yıldızlı):
  baslik*, url*, ozet*, kaynak_birimi*, guvenilirlik (0-1), guncellik (ISO tarih
  veya ""), dil ("tr"/"en"/...), notlar.

Birim eklemek = bu klasöre yeni .py dosyası + kurul.py'ye adını yazmak.
Birim sökmek = dosyayı silmek ya da kurulumdan çıkarmak. Çekirdeğe dokunmaz.
"""
from __future__ import annotations

import re
import time
from typing import Dict, List

AJAN = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def sonuc(baslik: str, url: str, ozet: str, birim: str,
          guvenilirlik: float = 0.5, guncellik: str = "",
          dil: str = "tr", notlar: str = "") -> Dict[str, object]:
    return {"baslik": baslik.strip(), "url": url.strip(),
            "ozet": re.sub(r"\s+", " ", ozet).strip()[:400],
            "kaynak_birimi": birim, "guvenilirlik": round(guvenilirlik, 2),
            "guncellik": guncellik, "dil": dil, "notlar": notlar}


def temiz_etiketler(metin: str) -> str:
    return re.sub(r"<.*?>", "", metin or "").strip()


def kis(s: str, n: int = 220) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def saat_damgasi() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def benzersizlestir(sonuclar: List[Dict]) -> List[Dict]:
    """Aynı URL tekrarlarını atar (çok dilli aramada mükerrer bilgi filtresi)."""
    gorulen, cikti = set(), []
    for s in sonuclar:
        anahtar = re.sub(r"[?#].*$", "", (s.get("url") or "").lower().rstrip("/"))
        if anahtar and anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        cikti.append(s)
    return cikti
