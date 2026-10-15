# -*- coding: utf-8 -*-
"""ARAMA YETENEĞİ — İstek olunca çağrılır, sürekli çalışmaz.

Varsayılan motor: DuckDuckGo (HTML uç noktası, API anahtarı gerektirmez,
tamamen yerel tarayıcı kurulumu istemez). Daha iyi bir arama modülü takmak
için bu klasörü silmek / yerine başkasını koymak yeterlidir (tak-sök).
"""
from __future__ import annotations

import html
import re
from typing import Dict, List

import requests

KULLANICI_AJANI = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _duckduckgo_ara(sorgu: str, adet: int = 6) -> List[Dict[str, str]]:
    r = requests.post("https://html.duckduckgo.com/html/",
                      data={"q": sorgu}, headers={"User-Agent": KULLANICI_AJANI},
                      timeout=15)
    r.raise_for_status()
    sayfa = r.text
    sonuc = []
    for blok in re.findall(
            r'<a rel="nofollow" class="result__a" href="(.*?)".*?>(.*?)</a>'
            r'.*?class="result__snippet"[^>]*>(.*?)</a>', sayfa, flags=re.S)[:adet]:
        url, baslik, ozet = blok
        # DDG yönlendirme linkini çöz
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            from urllib.parse import unquote
            url = unquote(m.group(1))
        temizle = lambda s: html.unescape(re.sub(r"<.*?>", "", s)).strip()
        sonuc.append({"baslik": temizle(baslik), "url": url.strip(),
                      "ozet": temizle(ozet)})
    return sonuc


def calistir(metin: str, **saglama) -> dict:
    """Karar merkezi/gönderici buradan çağırır. Dönen sözlük sohbete işlenir."""
    adet = int(saglama.get("adet", 6))
    # dış dünya onayı (kapıcı; ayarlarda serbest bırakıldıysa sormaz)
    try:
        from cekirdek.onay import TEKIL_KAPICI
        izin = TEKIL_KAPICI.denetle("web_ara", metin[:120],
                                    f"Hızlı arama yeteneği internete çıkmak istiyor.",
                                    alan="dis-dunya")
        if not izin.get("onayli"):
            return {"yanit": "", "sonuclar": [],
                    "hata": "İzin verilmedi: " + (izin.get("neden") or izin.get("kaynak", ""))}
    except Exception:
        pass
    # Güncel veri önce API'den denenir (kur/hava → birebir ölçüm, bayat blog yok)
    try:
        import sys, os
        _b = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "arastirmaci"))
        if _b not in sys.path:
            sys.path.insert(0, _b)
        from birimler.guncel_veri_birimi import ara as guncel_ara
        gu = guncel_ara({"sorgu": metin})
    except Exception:
        gu = []
    try:
        sonuclar = _duckduckgo_ara(metin, adet)
    except Exception as e:
        if gu:
            sonuclar = []
        else:
            return {"yanit": f"Arama başarısız: {e}", "sonuclar": []}
    satirlar = []
    for s in gu:
        satirlar.append(f"★ GÜNCEL VERİ — {s['baslik']}\n   {s['ozet']}\n"
                        f"   Kaynak: {s['kaynak_birimi']} | Zaman: {s['guncellik']}")
    for i, s in enumerate(sonuclar):
        satirlar.append(f"{i+1}. {s['baslik']}\n   {s['url']}\n   {s['ozet'][:220]}")
    if not satirlar:
        return {"yanit": f"'{metin}' için sonuç bulunamadı.", "sonuclar": []}
    return {"yanit": "\n\n".join(satirlar), "sonuclar": sonuclar,
            "guncel_veri": gu}


sozlesme = {
    "kod": "arama",
    "ad": "Arama (Dış Dünyaya Bakış)",
    "tur": "yetenek",
    "surum": "0.1",
    "aciklama": "İnternetten güncel bilgi arar. Çağrılınca çalışır, sonra kapanır.",
    "gorev_anahtarlari": ["ara", "bul", "güncel", "haber", "internet", "web",
                          "kaç lira", "son", "haberi"],
    "cagri_ornekleri": ["'bugün hava nasıl' → arama('bugün hava durumu')"],
    "calistir": calistir,
}
