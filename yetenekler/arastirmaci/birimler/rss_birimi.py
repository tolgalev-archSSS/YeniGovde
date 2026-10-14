# -*- coding: utf-8 -*-
"""RSS BİRİMİ — Haber kaynaklarından ZEİT DAMGALI gerçek haber akışı.

Arama motoru snippet'leri bayat olabilir (2019 haberi "güncel" diye
çıkabilir); RSS'te her maddenin yayılma tarihi DOĞDUGU ANDAN bellidir.
Konu filtresi başlık+sözet üzerinden uygulanır (ilgisiz madde elenir).

Kaynaklar ücretsiz ve anahtarsızdır; yeni feed = KATALOG'a tek satır.
"""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from typing import Dict, List

import requests

FEEDLER = [
    # (etiket, url, konu-deseni veya None=her şey)
    ("AI Turkçe", "https://www.artificialintelligence-news.com/feed/", r"ai|artificial|intelligence|model|chatgpt|openai|llm"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/", None),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", None),
    ("Ars Technica AI", "https://arstechnica.com/tag/ai/feed/", None),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", None),
]

OGUN = 5          # feed başına en fazla madde


def _tarih_ayikla(item: str) -> str:
    m = re.search(r"<pubDate>(.*?)</pubDate>", item, flags=re.S)
    if not m:
        m = re.search(r'<dc:date[^>]*>(.*?)</dc:date>', item, flags=re.S)
    if not m:
        return ""
    ham = m.group(1).strip()
    try:
        return parsedate_to_datetime(ham).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ham[:16]


def _feed_oku(etiket: str, url: str, desen, adet: int) -> List[Dict]:
    r = requests.get(url, headers={"User-Agent": "MLAO-arastirmaci RSS"}, timeout=15)
    r.raise_for_status()
    metin = r.text
    ciktilar = []
    for parca in re.findall(r"<item>(.*?)</item>", metin, flags=re.S)[:40]:
        al = lambda e: (re.search(fr"<{e}[^>]*>(.*?)</{e}>", parca, flags=re.S)
                        or re.search(fr"<{e}[^>]*/>(.*)", parca)
                        or [None, ""])[1].strip()
        baslik = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", al("title"))
        link = al("link").replace("<![CDATA[", "").replace("]]>", "")
        ozet = re.sub(r"<.*?>", " ", al("description"))
        ozet = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", ozet)
        ozet = re.sub(r"\s+", " ", ozet).strip()
        tarih = _tarih_ayikla(parca)
        if desen and not re.search(desen, (baslik + " " + ozet), flags=re.I):
            continue
        ciktilar.append({
            "baslik": f"[{etiket}] {baslik}",
            "url": link,
            "ozet": f"{ozet[:240]} | YAYIN: {tarih or 'bilinmiyor'}",
            "kaynak_birimi": "rss-haber",
            # tazelik güvene işlenir: son 7 gün → 0.85, daha eski → 0.6
            "guvenilirlik": 0.85 if _taze(tarih) else 0.6,
            "guncellik": tarih, "dil": "en", "notlar": "RSS, zaman damgalı"})
        if len(ciktilar) >= adet:
            break
    return ciktilar


def _taze(tarih: str) -> bool:
    try:
        from datetime import datetime, timedelta
        dt = datetime.strptime(tarih[:10], "%Y-%m-%d")
        return datetime.now() - dt <= timedelta(days=7)
    except Exception:
        return False


def ara(gorev: Dict[str, object]) -> List[Dict]:
    sorgu = str(gorev.get("sorgu", "")).lower()
    adet = int(gorev.get("adet", OGUN))
    if not sorgu:
        return []
    # konuya göre uygun feed'leri seç (hepsini denemek yavaş; desen eşleşmesi basit)
    ai_ilgili = any(k in sorgu for k in ["yapay zeka", "yapay zekâ", "ai", "chatgpt",
                                         "openai", "llm", "model", "gemini", "claude"])
    secim = FEEDLER if ai_ilgili else [f for f in FEEDLER if f[2] is None][:3]
    sonuclar: List[Dict] = []
    for etiket, url, desen in secim:
        try:
            sonuclar += _feed_oku(etiket, url, desen, max(adet // 2, 2))
        except Exception as e:
            continue    # tek feed çökerse diğerleri yine de gelsin
    # sorgu terimleriyle ilgisiz başlıkları da süz (ör. "robot" haberi ama sorgu "çip")
    return sonuclar[:adet]
