# -*- coding: utf-8 -*-
"""AKADEMIK BİRİM — OpenAlex + arXiv (ücretsiz, anahtarsız API'ler).

Akademik taramada makalenin kendisi birincil kaynaktır; atıf sayısı ve
yıl güvenirliğe çevrilir. Semantic Scholar/Crossref sonradan takılabilir.
"""
from __future__ import annotations

from typing import Dict, List

import requests


def _openalex(sorgu: str, adet: int) -> List[Dict]:
    r = requests.get("https://api.openalex.org/works",
                     params={"search": sorgu, "per-page": adet,
                             "sort": "relevance_score:desc"},
                     headers={"User-Agent": "MLAO-arastirmaci (yerel)"}, timeout=20)
    r.raise_for_status()
    cikti = []
    for w in r.json().get("results", []):
        yazarlar = ", ".join((a.get("author") or {}).get("display_name", "?")
                             for a in (w.get("authorships") or [])[:3])
        cikti.append({
            "baslik": w.get("title") or "(başlıksız)",
            "url": w.get("doi") or w.get("id", ""),
            "ozet": "{} ({}) | atıf: {} | yayın: {}".format(
                yazarlar, w.get("publication_year", "?"),
                w.get("cited_by_count", 0),
                (w.get("primary_location") or {}).get("source") or "-"),
            "kaynak_birimi": "openalex",
            "guvenilirlik": min(0.95, 0.5 + (w.get("cited_by_count", 0) ** 0.5) / 40),
            "guncellik": str(w.get("publication_year", "")),
            "dil": w.get("language", "") or "", "notlar": ""})
    return cikti


def _arxiv(sorgu: str, adet: int) -> List[Dict]:
    r = requests.get("http://export.arxiv.org/api/query",
                     params={"search_query": f"all:{sorgu}",
                             "max_results": adet, "sortBy": "relevance"},
                     timeout=25)
    r.raise_for_status()
    import re
    cikti = []
    for m in re.finditer(r"<entry>(.*?)</entry>", r.text, flags=re.S):
        parca = m.group(1)
        al = lambda etiket: (re.search(fr"<{etiket}>(.*?)</{etiket}>", parca,
                                       flags=re.S) or [None, ""])[1].strip()
        ozet = re.sub(r"\s+", " ", al("summary"))
        tarih = al("published")[:10]
        cikti.append({"baslik": re.sub(r"\s+", " ", al("title")),
                      "url": al("id"),
                      "ozet": f"{al('author').split('</name>')[0].replace('<name>', '')} … | {ozet[:250]}",
                      "kaynak_birimi": "arxiv", "guvenilirlik": 0.6,
                      "guncellik": tarih, "dil": "en", "notlar": "önbaskı"})
    return cikti


def _ilintili_mi(baslik: str, ozet: str, terimler) -> bool:
    """Konu akışı: başlık+özet en az bir sorgu terimini taşımalı.
    (arXiv 'all:' araması tam kelime avı yapar; 'Sümer' gibi Türkçe
    sözcükler makale yazar adlarında çıkıp alaka dışı sonuç üretebilir.)"""
    metin = (baslik + " " + ozet).lower()
    return any(t in metin for t in terimler if len(t) > 2)


def ara(gorev: Dict[str, object]) -> List[Dict]:
    sorgu = str(gorev.get("sorgu", "")).strip()
    adet = int(gorev.get("adet", 5))
    if not sorgu:
        return []
    # konu süzgeci için terimler (Türkçe karakterleri sadeleştir)
    import unicodedata, re as _re
    donusum = str.maketrans("çğıöşüâêîû", "cgiou saeiu".replace(" ", ""))
    sade = sorgu.lower().translate(donusum)
    sade = "".join(c for c in unicodedata.normalize("NFKD", sade)
                   if not unicodedata.combining(c))
    terimler = [t for t in _re.split(r"[^\w]+", sade) if len(t) > 2]
    # arXiv 'all:' tam kelime avı yapar; Türkçe kültür sorgularında yazar
    # adı/eşsesli terim gürültüsü üretir → yalnızca İngilizce görünürlü
    # terimler varsa arXiv'e git (OpenAlex alakalık sıralı ve dilli çalışır)
    ingilizce_terimler = {"flood", "myth", "myths", "legend", "sumer",
                          "sumerian", "babylonian", "gilgamesh", "noah",
                          "nuh", "torah", "quran", "genesis", "cuneiform"}
    arxiv_sor = None
    if any(t in ingilizce_terimler for t in terimler):
        anahtarlar = [t for t in terimler if t in ingilizce_terimler]
        arxiv_sor = " ".join(f'"{k}"' for k in anahtarlar[:3])
    sonuclar: List[Dict] = []
    for fonk, soru in ((_openalex, sorgu), (_arxiv, arxiv_sor)):
        if soru is None:
            continue
        try:
            ham = fonk(soru, max(adet * 3, adet))
            secilen = [s for s in ham
                       if _ilintili_mi(s["baslik"], s["ozet"], terimler)]
            # süzülen küme küçükse (en az 2) süzülmüşü, değilse ham listeyi al
            sonuclar += (secilen if len(secilen) >= 2 else ham)[:adet]
        except Exception as e:
            sonuclar.append({"baslik": f"[{fonk.__name__}] erişilemedi",
                             "url": "", "ozet": str(e)[:150],
                             "kaynak_birimi": "akademik-hata",
                             "guvenilirlik": 0.0, "guncellik": "", "dil": "",
                             "notlar": ""})
    return [s for s in sonuclar if s["guvenilirlik"] > 0]
