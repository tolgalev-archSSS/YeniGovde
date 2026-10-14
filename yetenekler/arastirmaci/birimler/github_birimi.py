# -*- coding: utf-8 -*-
"""GITHUB BİRİMİ — Açık kaynak proje/depo araması (resmi API, anahtar gerekmez).

Yıldız/güncellik/bakım sinyallerini guvenilirlik puanına çevirir.
"""
from __future__ import annotations

from typing import Dict, List

import requests

TEMEL = "https://api.github.com"


def ara(gorev: Dict[str, object]) -> List[Dict]:
    sorgu = str(gorev.get("sorgu", "")).strip()
    adet = int(gorev.get("adet", 6))
    if not sorgu:
        return []
    r = requests.get(f"{TEMEL}/search/repositories",
                     params={"q": sorgu, "sort": "stars", "order": "desc",
                             "per_page": adet},
                     headers={"Accept": "application/vnd.github+json",
                              "User-Agent": "MLAO-arastirmaci"}, timeout=20)
    r.raise_for_status()
    sonuclar = []
    for it in r.json().get("items", []):
        yildiz = it.get("stargazers_count", 0)
        guncel = it.get("pushed_at", "")[:10]
        # güven: yıldıza logaritmik + son itmeye göre tazelik bonusu
        guven = min(0.95, 0.35 + (yildiz ** 0.5) / 60.0)
        lisans = (it.get("license") or {}).get("spdx_id", "") or "belirsiz"
        sonuclar.append({
            "baslik": it.get("full_name", ""),
            "url": it.get("html_url", ""),
            "ozet": "{} | ⭐{} | lisans: {} | son itme: {}".format(
                it.get("description") or "(açıklama yok)", yildiz,
                lisans, guncel),
            "kaynak_birimi": "github", "guvenilirlik": round(guven, 2),
            "guncellik": guncel, "dil": it.get("language") or "",
            "notlar": f"yıldız={yildiz}, fork={it.get('forks_count', 0)}"})
    return sonuclar
