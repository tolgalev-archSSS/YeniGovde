# -*- coding: utf-8 -*-
"""ARAŞTIRMACI YETENEĞİ — Arama Kurulu'nun modül kabuğu (tak-sök uyumlu).

Karar merkezi 'arastirmaci' koduyla burayı çağırır. Eylem türleri:
  ara            → hızlı tek birim taraması (web)
  kurul_ara      → kategoriye göre uzman birimlerle paralel tarama + derleme
  detayli_ara    → çok dilli / perspektifli derin tarama (Ağır model derler)
  sayfa_oku      → bir URL'nin metnini çıkarır (basit kazıyıcı; Crawl4AI
                   sonradan takılabilir, sözleşme aynı kalır)

Dikkat: Bu yetenek dış dünyaya çıkar → panelde ONAY kartı ister (kapıcı
EL'dekiyle aynı mekanizmayı kullanır; ilk sürümde eylem bazlı oturum izni).
"""
from __future__ import annotations

import os
import re
from typing import Dict

_KOK = os.path.dirname(os.path.abspath(__file__))
if _KOK not in __import__("sys").path:
    __import__("sys").path.insert(0, _KOK)   # tek klasör yolu → karışıklık yok

from kurulus import KURULUM                   # modül içi ayar (gömülü)

_kurul_nesnesi = None


def _kurul():
    global _kurul_nesnesi
    if _kurul_nesnesi is None:
        from kurul import Kurul
        _kurul_nesnesi = Kurul(_KOK)
    return _kurul_nesnesi


def _gorev_ayristir(metin: str) -> Dict[str, object]:
    """Karar merkezi JSON gönderirse onu, düz metin gelirse 'ara' say."""
    try:
        import json
        j = json.loads(str(metin)) if str(metin).strip().startswith("{") else None
        if isinstance(j, dict):
            return j
    except Exception:
        pass
    # duz metin: '... | tercih: ...' veya 'tercihim: ...' ayrıştır
    import re as _re
    t = str(metin)
    tercih = ""
    m = _re.search(r"(?:tercim?\s*:|tercihim[:\s]+)(.+)$", t, flags=_re.I)
    if m:
        tercih = m.group(1).strip()
        t = t[:m.start()].strip(" |")
    girdi = {"eylem": "ara", "sorgu": t}
    if tercih:
        girdi["tercih"] = tercih
    return girdi


def _onay_al(eylem: str, hedef: str, aciklama: str) -> dict:
    """Dış dünyaya çıkmadan önce kapıcıdan izin iste (ayarlar→arama.onay_serbest
    açıksa kapıcı kendiliğinden onaylar; oturum/kalıcı izinler de tanınır)."""
    try:
        from cekirdek.onay import TEKIL_KAPICI
        return TEKIL_KAPICI.denetle(eylem, hedef, aciklama, alan="dis-dunya")
    except Exception:
        return {"onayli": True, "kaynak": "kapici_yok", "neden": ""}


def calistir(metin: str, **saglama) -> dict:
    gorev = _gorev_ayristir(metin)
    ayar_adet = 6
    try:
        from cekirdek import yapilandirma
        ayar_adet = int(yapilandirma.yukle().get("arama", {}).get("varsayilan_adet", 6))
    except Exception:
        pass
    gorev.setdefault("adet", KURULUM.get("varsayilan_adet", ayar_adet))
    eylem = str(gorev.get("eylem", "ara"))
    sorgu = str(gorev.get("sorgu", "")).strip()
    adet = int(gorev.get("adet", KURULUM.get("varsayilan_adet", ayar_adet)))
    if not sorgu and eylem != "program_listele":
        return {"basarili": False, "hata": "Sorgu boş.", "yanit": ""}

    # DIŞ DÜNYA ONAYI: arama/sayfa okuma internete çıkan işlemlerdir.
    izin = _onay_al(eylem if eylem in ("sayfa_oku",) else "web_ara",
                    sorgu[:120], f"Araştırmacı dış dünyaya çıkmak istiyor ({eylem}).")
    if not izin.get("onayli"):
        return {"basarili": False, "hata": "İzin verilmedi: " +
                (izin.get("neden") or izin.get("kaynak", "")), "yanit": ""}

    kurul = _kurul()
    if eylem == "sayfa_oku":
        return _sayfa_oku(sorgu)

    detayli = eylem == "detayli_ara" or bool(gorev.get("detayli"))
    tercih = str(gorev.get("tercih", "")).strip()
    filtre = list(gorev.get("filtre_url_icindekiler") or [])

    # HABER turu: RSS birimi zorlanir (zeit damgali gercek haber akisi)
    zorla = ""
    import importlib.util as _ilu
    _kp = os.path.join(_KOK, "kurul.py")
    _spec = _ilu.spec_from_file_location("arastirmaci_kurul", _kp)
    _km = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_km)
    kategori_belirle = _km.kategori_belirle
    if kategori_belirle(sorgu) == "haber" and "rss_birimi" in kurul.birimleri():
        zorla = "rss_birimi"

    veri = kurul.topla(sorgu, detayli=detayli, adet=adet,
                       zorla_birim=zorla, gorev_filtre=filtre)

    # URUN INCELEME: bulunan urun sayfası URL'lerinin İÇİNE gir (puan+yorum)
    if (kategori_belirle(sorgu) == "urun_inceleme"
            or any(k in sorgu.lower() for k in ["incele", "puanla", "yorum"])) \
            and "sayfa_oku_birimi" in kurul.birimleri():
        aday_url = [s["url"] for s in veri["sonuclar"]
                    if s.get("url", "").startswith("http")
                    and any(t in s["url"].lower() for t in
                            ("hepsiburada", "trendyol", "amazon", "vatan",
                             "mediamarkt", "cimri", "akakce", "n11", "pttavm"))]
        if aday_url:
            derin = kurul._birimler["sayfa_oku_birimi"].ara(
                {"urler": aday_url[:3], "filtre_url_icindekiler": filtre})
            if derin:
                veri["sonuclar"] = derin + veri["sonuclar"]
                veri["birimler"].append("sayfa_oku(derin)")
    kanit = kurul.kanit_dosyasi(veri)
    ekler = []
    if tercih:
        ekler.append(f"BU İSTEĞİN TERCİHİ: {tercih}")
    try:
        from cekirdek.hafiza_kopru import tercihleri_getir
        bellek = tercihleri_getir()
        if bellek:
            ekler.append("KULLANICININ GEÇMİŞ TERCİHLERİ (hafıza):\n" + bellek)
    except Exception:
        pass
    if ekler:
        kanit = "\n".join(ekler) + "\n\n" + kanit
    ozet = (f"{veri['kategori']} kategorisi, {len(veri['sonuclar'])} kanıt, "
            f"birimler: {', '.join(veri['birimler'])}"
            + (f", tercih: {tercih[:40]}" if tercih else ""))
    yanit = (f"{ozet}\n\nKANIT DOSYASI:\n{kanit[:6000]}")
    return {"basarili": True, "yanit": yanit, "ozet": ozet,
            "veri": veri, "model_notu": "derlemeyi AĞIR model yapmalı"}


def _sayfa_oku(url: str) -> dict:
    import requests
    if not re.match(r"https?://", url):
        return {"basarili": False, "hata": "Geçerli http(s) adresi gerekli.",
                "yanit": ""}
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        metin = re.sub(r"<(script|style).*?</\1>", " ", r.text, flags=re.S | re.I)
        metin = re.sub(r"<.*?>", " ", metin)
        metin = re.sub(r"\s+", " ", metin).strip()
        return {"basarili": True, "yanit": metin[:8000],
                "ozet": f"{url} okundu ({len(metin)} karakter)"}
    except Exception as e:
        return {"basarili": False, "hata": f"Sayfa okunamadı: {e}", "yanit": ""}


sozlesme = {
    "kod": "arastirmaci",
    "ad": "Araştırmacı (Arama Kurulu)",
    "tur": "yetenek",
    "surum": "0.2",
    "aciklama": "Uzman birimli arama kurulu: web/GitHub/akademik/güncel veri; "
                "detaylı aramada çok dilli ve perspektifli tarama yapar.",
    "gorev_anahtarlari": ["ara", "kurul", "derin ara", "detaylı", "kıyaslama",
                          "karşılaştır", "makale", "github", "fiyat", "haber",
                          "kim", "perspektif", "akademik"],
    "cagri_ornekleri": [
        "'şu açık kaynak hafıza sistemlerini karşılaştır' → arastirmaci("
        "{\"eylem\":\"kurul_ara\",\"sorgu\":\"open source memory llm\"})",
        "'nuh tufanı farklı kaynaklarda nasıl geçer' → arastirmaci({\"eylem\":"
        "\"detayli_ara\",\"sorgu\":\"Nuh tufanı\"})",
    ],
    "calistir": calistir,
}
