# -*- coding: utf-8 -*-
"""DOSYA YAZMA YETENEĞİ — İstenen içeriği dosyaya kaydeder.

Güvenlik: yazmalar yalnızca `veri/cikti/` altına yapılır (göbekli bir yol
verilse bile klasör dışına çıkamaz). Daha gelişmiş bir dosya yeteneği takmak
için bu klasörü silmek yeterlidir.
"""
from __future__ import annotations

import os
import re

from cekirdek import yapilandirma

CIKTI_DIZIN = os.path.join(yapilandirma.VERI_DIZIN, "cikti")


def _guvenli_yol(dosya_adi: str) -> str:
    ad = re.sub(r"[^\w\d\-\.\u0100-\u017F /]", "_", dosya_adi.strip())
    ad = ad.replace("..", "_")
    tam = os.path.abspath(os.path.join(CIKTI_DIZIN, ad))
    if not tam.startswith(os.path.abspath(CIKTI_DIZIN)):
        tam = os.path.join(CIKTI_DIZIN, os.path.basename(ad))
    return tam


def calistir(metin: str, **saglama) -> dict:
    """metin: yazılacak içerik. saglama.dosya: hedef ad (opsiyonel)."""
    os.makedirs(CIKTI_DIZIN, exist_ok=True)
    dosya = saglama.get("dosya") or ""
    if not dosya:
        ilk = metin.strip().splitlines()[0] if metin.strip() else "not"
        dosya = re.sub(r"\W+", "_", ilk[:40], flags=re.UNICODE) + ".txt"
    yol = _guvenli_yol(dosya)
    try:
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)
        return {"yanit": f"Dosya yazıldı → {yol} ({len(metin)} karakter)",
                "yol": yol}
    except Exception as e:
        return {"yanit": f"Yazma hatası: {e}", "yol": ""}


sozlesme = {
    "kod": "dosya_yazma",
    "ad": "Dosya Yazma (El)",
    "tur": "yetenek",
    "surum": "0.1",
    "aciklama": "İçeriği veri/cikti/ altındaki dosyalara yazar.",
    "gorev_anahtarlari": ["dosyaya yaz", "kaydet", "not al", "çıktı dosyası",
                          "raporu yaz"],
    "cagri_ornekleri": ["'bu analizi rapor.txt dosyasına yaz' → "
                        "dosya_yazma(içerik, dosya='rapor.txt')"],
    "calistir": calistir,
}
