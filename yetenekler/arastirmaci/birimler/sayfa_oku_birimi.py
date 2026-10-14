# -*- coding: utf-8 -*-
"""SAYFA OKU BİRİMİ — URL'lerin İÇİNE girer: ürün sayfası, yorum bölümü, haber.

Ürün inceleme akışının ikinci gözü: arama snippet'i yüzeyseldir; gerçek
puan/yorum/özellik bilgisi sayfaların içindedir. Basit regex kazıyıcı
(trafik koruması olmayan kaynaklarda çalışır; Crawl4AI sonradan takılabilir,
sözleşme aynı kalır: ara(gorev) -> Liste[Sonuc]).

gorev["filtre_url_icindekiler"]: yalnız bu dizeleri içeren URL'ler okunur
(ör. ['hepsiburada.com', 'trendyol.com']) — gelişmiş kullanıcı ayarı.
"""
from __future__ import annotations

import html as _h
import re
from typing import Dict, List

import requests

AJAN = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"}


def _metin(url: str) -> str:
    r = requests.get(url, headers=AJAN, timeout=20)
    r.raise_for_status()
    t = re.sub(r"<(script|style|noscript).*?</\1>", " ", r.text, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return _h.unescape(re.sub(r"\s+", " ", t))


def _skor_ayikla(metin: str):
    """'4,3 / 5', '4.3 yıldız', '(1.234 değerlendirme)' gibi örüntüler."""
    skor = None
    m = re.search(r"(\d[.,]\d)\s*(?:\/\s*5|star|yıldız|puan)", metin, flags=re.I)
    if not m:
        m = re.search(r"(?:ortalam|rating|skor)[^\d]{0,12}(\d[.,]\d)", metin, flags=re.I)
    if m:
        try:
            skor = float(m.group(1).replace(",", "."))
            if not 0 < skor <= 5:
                skor = None
        except ValueError:
            skor = None
    adet = None
    m2 = re.search(r"([\d.,]+\d)\s*(değerlendirme|yorum|review|yıldız sayısı)",
                   metin, flags=re.I)
    if m2:
        try:
            adet = int(m2.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            adet = None
    return skor, adet


def _yorum_ornekleri(metin: str) -> str:
    """Yorum bloklarından kısa örnek cümleler topla (olumlu/olumsuz koku)."""
    cumleler = []
    for kelime, isaret in [("memnun", "+"), ("beğendim", "+"), ("kaliteli", "+"),
                           ("tavsiye", "+"), ("pişman", "-"), ("bozuk", "-"),
                           ("iade", "-"), ("kötü", "-"), ("kopdu", "-"),
                           ("gürültü engelleme", "ozellik")]:
        m = re.search(r"[^.!?]{20,140}\b" + kelime + r"\b[^.!?]{0,80}", metin, flags=re.I)
        if m:
            cumleler.append(f"{isaret}: …{m.group(0).strip()[:120]}…")
        if len(cumleler) >= 4:
            break
    return " || ".join(cumleler)


def ara(gorev: Dict[str, object]) -> List[Dict]:
    url_listesi = gorev.get("urler") or []
    filtre = [f.lower() for f in (gorev.get("filtre_url_icindekiler") or [])]
    if isinstance(url_listesi, str):
        url_listesi = [url_listesi]
    cikti: List[Dict] = []
    for url in list(url_listesi)[:6]:
        url = str(url).strip()
        if not url.startswith("http"):
            continue
        if filtre and not any(f in url.lower() for f in filtre):
            continue          # kullanıcı site filtresi koydu → dışını okuma
        try:
            metin = _metin(url)
        except Exception as e:
            cikti.append({"baslik": f"[sayfa açılamadı] {url[:60]}", "url": url,
                          "ozet": str(e)[:120], "kaynak_birimi": "sayfa-oku-hata",
                          "guvenilirlik": 0.0, "guncellik": "", "dil": "",
                          "notlar": ""})
            continue
        skor, adet = _skor_ayikla(metin)
        yorum = _yorum_ornekleri(metin)
        baslik_m = re.search(r"<title[^>]*>(.*?)</title>", metin, flags=re.S)
        ozet = []
        if skor:
            ozet.append(f"PUAN: {skor}/5" + (f" ({adet} değerlendirme)" if adet else ""))
        if yorum:
            ozet.append("YORUM ÖRNEKLERİ: " + yorum)
        if not ozet:
            ozet.append("Sayfa metninden öne çıkanlar: " + metin[:300])
        cikti.append({
            "baslik": (baslik_m.group(1).strip()[:90] if baslik_m else url[:70]),
            "url": url, "ozet": " | ".join(ozet)[:400],
            "kaynak_birimi": "sayfa-oku",
            "guvenilirlik": 0.8 if skor else 0.55,   # sayfalanan bilgi birebir
            "guncellik": "", "dil": "tr",
            "notlar": "URL içeriği doğrudan okundu"})
    return cikti
