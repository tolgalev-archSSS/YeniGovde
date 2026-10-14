# -*- coding: utf-8 -*-
"""WEB BİRİMİ — Genel internet araması (ddgs = DuckDuckGo çok motorlu toplayıcı).

Önerilen açık kaynak çözüm: ddgs (9.4/10, araştırma günlüğüne bakınız).
Kurulu değilse eski HTML kazıma yöntemine düşer → birim asla çökmez.

İngilizce destekli arama: Türkçe sorgu İngilizceye çevrilip EK ARAMA olarak
da taranır (ayarlar → arama.ingilizce_ara; detaylı aramada her zaman aktif).
Sonuçlar tekilleştirilir ve hangi dilde bulunduğunu gösteren etiket taşır.
"""
from __future__ import annotations

import re
from typing import Dict, List


def _dil_ingilizce_ara_acik(detayli: bool) -> bool:
    """Ayarlar → arama.ingilizce_ara; detaylı aramada her zaman aktif."""
    if detayli:
        return True
    try:
        from cekirdek import yapilandirma
        return bool(yapilandirma.yukle().get("arama", {}).get("ingilizce_ara", True))
    except Exception:
        return True


def ingilizce_cevir(sorgu: str) -> str:
    """Türkçe sorguyu İngilizceye çevirmeyi dener (yoksa aynen döner).

    Sıra: 1) Ollama rutin model (en iyi kalite), 2) translatepy (açık kaynak,
    Google/DeepL çeviri API'lerini saran yerel paket), 3) sorgunun kendisi.
    """
    t = sorgu.strip()
    if not t or all(ord(c) < 128 for c in t):
        return ""                      # zaten ASCII → İngilizce kabul, ek arama yok
    # 1) Ollama çevirisi
    try:
        from cekirdek import yapilandirma
        from cekirdek.ollama_kontrol import OllamaIstemcisi
        ayar = yapilandirma.yukle()
        model = ayar["modeller"].get("rutin_model")
        if model:
            istemci = OllamaIstemcisi(ayar["ollama"]["adres"])
            if istemci.canli_mi():
                cevap = istemci.uretim(
                    model,
                    [{"role": "user", "content":
                      f"Aşağıdaki Türkçe arama sorgusunu doğal bir İngilizce arama "
                      f"sorgusuna çevir. Yalnızca çeviriyi yaz, açıklama yazma:\n{t}"}],
                    sistem="Sen bir arama motoru çevirmenisin. Tek satır çıktı ver.",
                )
                cevap = (cevap or "").strip().splitlines()[0] if cevap else ""
                if cevap and len(cevap) < 200:
                    return cevap
    except Exception:
        pass
    # 2) translatepy yedeği
    try:
        from translatepy import Translator
        cev = Translator().translate(t, "en", "tr").result()
        if cev:
            return str(cev).strip()
    except Exception:
        pass
    return ""                          # çevrilemedi → yalnız Türkçe aranır

try:
    from ddgs import DDGS  # yeni paket adı
except ImportError:
    try:
        from duckduckgo_search import DDGS  # eski ad (geriye dönük uyum)
    except ImportError:
        DDGS = None


def _tek_arama(sorgu: str, bolge: str, adet: int, dil_etiketi: str) -> List[Dict]:
    """Tek bir sorguyu tek bölgede tarar; standart sözlük listesi döner."""
    sonuclar: List[Dict] = []
    if DDGS is not None:
        try:
            with DDGS() as d:
                try:
                    akis = d.text(sorgu, region=bolge, safeness="off", max_results=adet)
                except TypeError:      # eski/sürüm farkı: sade parametrelere düş
                    akis = d.text(sorgu, max_results=adet)
            for s in akis:
                sonuclar.append({
                    "baslik": s.get("title", ""), "url": s.get("href", ""),
                    "ozet": s.get("body", ""), "kaynak_birimi": "web",
                    "guvenilirlik": 0.5, "guncellik": "", "dil": dil_etiketi,
                    "notlar": ""})
            return sonuclar
        except Exception:
            pass  # yedek yönteme düş
    # Yedek: DDG HTML uç noktası (ddgs kurulu değilse)
    import html as _h
    import re
    import requests
    try:
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": sorgu},
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
    except Exception:
        return sonuclar
    for blok in re.findall(
            r'<a rel="nofollow" class="result__a" href="(.*?)".*?>(.*?)</a>'
            r'.*?class="result__snippet"[^>]*>(.*?)</a>', r.text, flags=re.S)[:adet]:
        url, baslik, ozet = blok
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            from urllib.parse import unquote
            url = unquote(m.group(1))
        sonuclar.append({"baslik": _h.unescape(re.sub("<.*?>", "", baslik)),
                         "url": url.strip(),
                         "ozet": _h.unescape(re.sub("<.*?>", "", ozet))[:220],
                         "kaynak_birimi": "web", "guvenilirlik": 0.5,
                         "guncellik": "", "dil": dil_etiketi, "notlar": ""})
    return sonuclar


def _fiyat_ayikle(metin: str):
    """Sorgudaki fiyat bandını çıkar: '5000 tl' → 5000.0 (yoksa None)."""
    m = re.search(r"(\d[\d.,]*)\s*(tl|₺|lira)\b", metin.lower())
    if not m:
        return None
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _model_kodu(sorgu: str) -> str:
    """Sorgudaki olası ürün/model kodunu ayıkla (harf+rakam karışımı token)."""
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}", sorgu):
        if any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            return tok.lower().strip("-")
    return ""


def _varyant_etiketi(baslik: str, hedef_kod: str) -> str:
    """Başlıkta hedef model kodu geçiyor mu? ('kopya/yanlış varyant' filtresi)."""
    if not hedef_kod:
        return ""
    sade = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")  # 7'ye 7
    t = baslik.lower().translate(sade)
    return "hedef-model-var" if hedef_kod in t else "model-kodu-yok"


def ara(gorev: Dict[str, object]) -> List[Dict]:
    sorgu = str(gorev.get("sorgu", "")).strip()
    dil = str(gorev.get("dil", "tr-auto"))
    adet = int(gorev.get("adet", 6))
    detayli = bool(gorev.get("detayli")) or dil.startswith(("ja", "de", "ar", "fa", "fr"))
    if not sorgu:
        return []
    # Kurulun gönderdiği Türkçe kültür/motif sorgularını İngilizce evrensel
    # terimlere çevir (arXiv/OpenAlex/EN arama motorları TR terimi tanımaz;
    # Nuh→Noah, Sümer→Sumerian, Gılgamış→Gilgamesh, tufan→flood myth).
    _TR_TO_EN = {
        "nuh": "noah", "tufan": "great flood", "tufanı": "flood",
        "tüfan": "great flood", "sümer": "sumerian", "şümer": "sumerian",
        "gilgamesh": "gilgamesh", "gılgamış": "gilgamesh",
        "kutsal kitaplar": "holy scriptures", "kuran": "quran",
        "tevrat": "torah", "zabur": "psalms", "incil": "gospels bible",
        "mitoloji": "mythology", "yaratılış": "creation myth",
        "peygamber": "prophet", "gemİ": "ark", "gemi": "ark",
        "tılsım": "talisman", "büyü": "magic",
    }
    kelimeler = [w.strip(".,?!'\"()[]{}«»\"").lower() for w in re.split(r"\s+", sorgu)] if False else None

    def _ingilizcelestir(metin: str) -> str:
        donusum = str.maketrans("çğıöşü", "cgiosu")  # tek katman: alt satırda lower() var
        sade = metin.lower().translate(donusum)
        parcalar = re.split(r"(\W+)", sade)
        cevrilen = [(_TR_TO_EN.get(p, p)) for p in parcalar]
        cikti = "".join(cevrilen)
        return cikti if cikti != sade else ""
    ing_sorgu = _ingilizcelestir(sorgu) or ""
    ana_bolge = {"tr": "tr-tr", "en": "en-us", "ja": "ja-jp", "de": "de-de",
                 "ar": "ar-ar", "fa": "fa-ir", "fr": "fr-fr"}.get(dil.split("-")[0], "tr-tr")
    # 1) Ana dilde arama
    sonuclar = _tek_arama(sorgu, ana_bolge, adet, dil.split("-")[0])
    # 2) İngilizce destekli arama: TR sorgunun İngilizcesiyle EK tarama
    if _dil_ingilizce_ara_acik(detayli):
        ing = ingilizce_cevir(sorgu)
        if ing and ing.lower() != sorgu.lower():
            ek = _tek_arama(ing, "en-us", adet, "en")
            gorulen = {s["url"].lower().rstrip("/") for s in sonuclar}
            yeni = [s for s in ek
                    if s["url"].lower().rstrip("/") not in gorulen]
            for s in yeni:
                s["notlar"] = f"İngilizce arama ile bulundu (sorgu: {ing})"
            sonuclar += yeni
            if yeni:
                sonuclar.insert(0, {
                    "baslik": "[Birim notu]", "url": "",
                    "ozet": f"Türkçe sorguya ek olarak İngilizce de tarandı: '{ing}' "
                            f"→ {len(yeni)} yeni kaynak.",
                    "kaynak_birimi": "web", "guvenilirlik": 0.9,
                    "guncellik": "", "dil": "tr+en", "notlar": "yöntem bilgisi"})
    # --- Ürün araması güçlendirmeleri (kategori: urun) ---
    kategori = str(gorev.get("kategori", ""))
    site_onceligi = list(gorev.get("site_onceligi") or [])
    hedef_kod = _model_kodu(sorgu) if kategori == "urun" else ""
    fiyat_tavan = _fiyat_ayikle(sorgu) if kategori == "urun" else None
    if kategori == "urun":
        for s in sonuclar:
            etiket = _varyant_etiketi(s["baslik"], hedef_kod)
            parcalar = []
            if etiket:
                parcalar.append(etiket + (f" (kod: {hedef_kod})" if hedef_kod else ""))
            if s.get("notlar"):
                parcalar.append(s["notlar"])
            s["notlar"] = " | ".join(parcalar)
        # istek üzerine site önceliği: TR perakende/fiyat siteleri öne alınır
        def _site_sirasi(s):
            u = (s.get("url") or "").lower()
            for i, site in enumerate(site_onceligi):
                if site.lower() in u:
                    return i
            return len(site_onceligi)
        onlar = [s for s in sonuclar if _site_sirasi(s) < len(site_onceligi)]
        diger = [s for s in sonuclar if _site_sirasi(s) >= len(site_onceligi)]
        sonuclar = onlar + diger
        if site_onceligi and onlar:
            sonuclar.insert(0, {
                "baslik": "[Birim notu]", "url": "",
                "ozet": ("Ürün araması öncelikli Türk sitelerinden süzüldü: "
                         + ", ".join(site_onceligi)
                         + (f". Hedef model kodu: '{hedef_kod}'." if hedef_kod else ".")
                         + (f" Fiyat tavanı: {fiyat_tavan:.0f} TL — başlıkta fiyat "
                            f"doğrulanamadı, derleme aşamasında kontrol edilsin."
                            if fiyat_tavan else "")),
                "kaynak_birimi": "web", "guvenilirlik": 0.9,
                "guncellik": "", "dil": "tr", "notlar": "yöntem bilgisi"})
    return sonuclar
