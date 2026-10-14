# -*- coding: utf-8 -*-
"""KÜLTÜREL DIL BİRİMİ — Çok dilli tarama + perspektif analizi (TASARIMLAR/arama_derinlestirme.md).

Kimono örneği: Türkçe kaynak kıt → terimin kendi dilinde (ja) de aranır.
Nuh Tufanı örneği: İslam / Hristiyanlık / Yahudilik / Sümer perspektifleri
ayrı ayrı taranır; ortak çekirdek-farklılıklar model tarafından derlenir.

Bu birim AĞIR aramalarda devreye girer (detaylı arama, motif/kültür terimi).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List

PERSPEKTIF_KATALOGU = {
    "dinler_ve_motifler": {
        "islam": ["{terim} islam kur'an kaynak", "{terim} diyanet",
                  "{terim} islam ansiklopedisi"],
        "hristiyanlik": ["{terim} christianity bible", "{terim} hristiyanlık kutsal kitap"],
        "yahudilik": ["{terim} judah torah talmud", "{terim} yahudilik tora"],
        "sumer_babil": ["{terim} sumer cuneiform mythology",
                        "{terim} gilgamesh tablet", "{terim} antik mezopotamya"],
    },
    "kultur_terimleri": {
        "kendi_dili": ["{terim} 着物 japanisch", "{terim} kimono history original"],
        "akademik": ["{terim} cultural studies comparative"],
    },
}

DIL_TAHMIN_EGISTIRMESI = {
    # terim kökeni ipuçları → ek dilde sorgu şablonu
    "kimono": ("ja", "着物"), "sushi": ("ja", "寿司"), "ramen": ("ja", "ラーメン"),
    "torah": ("he", "תורה"), "quran": ("ar", "القرآن"), "flood": ("en", "deluge myth"),
    "nuh": ("arc", "طوفان نوح"), "tufan": ("en", "great flood mythology"),
}


def perspektif_haritasi(terim: str) -> Dict[str, List[str]]:
    """Terimin ait olduğu olası kümenin sorgu şablonlarını döndürür."""
    t = terim.lower()
    harita: Dict[str, List[str]] = {}
    if any(k in t for k in ["tufan", "flooding", "gilgamesh", "nuh", "noah",
                           "yaratılış", "mitoloji", "peygamber", "kutsal"]):
        harita["dinler_ve_motifler"] = []
        for kaynaklar in PERSPEKTIF_KATALOGU["dinler_ve_motifler"].values():
            harita["dinler_ve_motifler"] += [s.format(terim=terim) for s in kaynaklar]
    if t in DIL_TAHMIN_EGISTIRMESI or len(t.split()) == 1 and not t.isascii():
        kod, yerel = DIL_TAHMIN_EGISTIRMESI.get(t, ("", ""))
        harita["kendi_dili"] = [f"{terim} {yerel}".strip(), f"{terim} origin history"]
    return harita


def ara(gorev: Dict[str, object]) -> List[Dict]:
    """gorev: {'sorgu':..., 'perspektifler': [liste], 'web_ara': fonksiyon}

    web_ara fonksiyonu kurul tarafından enjekte edilir (birimler iç içe geçer).
    """
    terim = str(gorev.get("sorgu", "")).strip()
    web_ara = gorev.get("web_ara")
    if not callable(web_ara) or not terim:
        return []
    harita = perspektif_haritasi(terim)
    perspektifler = gorev.get("perspektifler") or list(harita.keys())
    sonuclar: List[Dict] = []
    for bakis in perspektifler:
        sorgular = harita.get(bakis) or [terim]
        for s in sorgular[:6]:
            try:
                for r in web_ara({"sorgu": s, "dil": "en" if bakis != "islam" else "tr-auto",
                                  "adet": 3}):
                    r["notlar"] = (r.get("notlar", "") +
                                   f" | perspektif:{bakis}").strip(" |")
                    sonuclar.append(r)
            except Exception:
                continue
    return sonuclar


def analiz_raporu(sonuclar: List[Dict]) -> str:
    """Perspektif bazlı gruplama — modele gönderilmeden önce yapı iskelesi."""
    gruplar: Dict[str, List[Dict]] = {}
    for s in sonuclar:
        p = re.search(r"perspektif:(\w+)", s.get("notlar", ""))
        gruplar.setdefault(p.group(1) if p else "genel", []).append(s)
    satirlar = []
    for p, liste in gruplar.items():
        benzersiz_url = {l["url"] for l in liste if l.get("url")}
        satirlar.append(f"[{p}] {len(liste)} sonuç, {len(benzersiz_url)} özgün kaynak")
    return "\n".join(satirlar)
