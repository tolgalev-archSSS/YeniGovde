# -*- coding: utf-8 -*-
"""KURUL — Arama Kurulu orkestratörü.

Akış (TASARIMLAR/arama_kurulu.md):
  istek → görev analizi (kategori) → uzman birim seçimi → paralel tarama
  → birleştirme + mükerrer filtresi → puanlı kanıt dosyası → modele derleme.

Birim listesi BURADAN yönetilir; bir dosyayı silmek birimi sökmez ama
listeden çıkarmak anında devre dışı bırakır. Yeni birim = klasöre dosya +
BURAYA tek satır. Çekirdeğe dokunuş yok.
"""
from __future__ import annotations

import importlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

KATEGORI_BIRIMLER = {
    "genel":        ["web_birimi"],
    "kisi":         ["web_birimi"],
    "urun":         ["web_birimi", "guncel_veri_birimi"],
    "guncel_veri":  ["guncel_veri_birimi", "web_birimi"],
    "akademik":     ["akademik_birimi", "web_birimi"],
    "yazilim":      ["github_birimi", "web_birimi"],
    "kultur_motif": ["kulturel_dil_birimi", "web_birimi", "akademik_birimi"],
    "haber":        ["rss_birimi", "web_birimi", "guncel_veri_birimi"],
    "urun_inceleme": ["web_birimi", "sayfa_oku_birimi"],
}

_KATEGORI_IPUCLARI = [
    ("guncel_veri", r"\bhava\b|\bdolar|\beuro|\bkur\b|\bkaç tl|\bsıcaklık|\bstrelin"),
    ("haber", r"\bhaber\b|son dakika|\bgündem\b|gelişme|haberi|\bnews\b|"
              r"yapay zekâ|yapay zekaa?|\bai\b|chatgpt|openai|claude|gemini|"
              r"llama|mistral|midjourney"),
    ("kultur_motif", r"\btufan\b|\bnuh\b|mitoloji|\bgilgamesh\b|kutsal|din\b|"
                     r"perspektif|karşılaştır.*(inan|din|kültür)|kimono|sushi|"
                     r"\bisa\b|\byesus\b|incil|\bkuran\b|meryem|peygamber|"
                     r"dinler|tevrat|zabur"),
    ("akademik", r"\bmakale\b|\baraştırma (sonucu|makalesi)\b|\batıf\b|"
                 r"\bpaper\b|\barxiv\b|bilimsel|\btez\b"),
    ("yazilim", r"github|açık kaynak|\bproje\b.*\bkütüphane\b|\brepo\b|"
                r"\bpython kütüphanesi\b|framework|\baraç bul\b"),
    ("urun_inceleme", r"incele|\bpuanla\b|yorumları?(n\d*)?\s*(hesab|dikkat|göz)|"
                      r"detayl\w*\s*incele|kullanıcı yorumu"),
    ("urun", r"\bfiyat\b|\bal\b.*öner|\bbütçe\b|\bkarşılaştır.*ürün|"
             r"\bcimri|\bakakçe|trendyol|hepsiburada|\bbandında\b|\bbandı\b|"
             r"\bkadar\b.*(tl|lira)|\bolan\s*(kulaklık|telefon|bilgisayar|saat|tv|klavye|mouse|monitör|tablet)\b"),
    ("kisi", r"\bkim\b|\bkişi\b|profil\b|\bkullanıcı adı\b|sosyal medya"),
]


def kategori_belirle(metin: str) -> str:
    t = metin.lower()
    for kategori, desen in _KATEGORI_IPUCLARI:
        if re.search(desen, t):
            return kategori
    return "genel"


class Kurul:
    def __init__(self, kok_klasor: str):
        self._birimler: Dict[str, object] = {}
        import sys, os
        if kok_klasor not in sys.path:
            sys.path.insert(0, kok_klasor)
        for ad in ("web_birimi", "github_birimi", "akademik_birimi",
                   "guncel_veri_birimi", "kulturel_dil_birimi",
                   "rss_birimi", "sayfa_oku_birimi"):
            try:
                self._birimler[ad] = importlib.import_module(f"birimler.{ad}")
            except Exception as e:
                print(f"[Kurul] {ad} yüklenemedi: {e}")

    def birimleri(self) -> List[str]:
        return sorted(self._birimler)

    @staticmethod
    def _guncel_veri_acik() -> bool:
        try:
            from cekirdek import yapilandirma
            return bool(yapilandirma.yukle().get("arama", {})
                        .get("guncel_veri_birimi_acik", True))
        except Exception:
            return True

    @staticmethod
    def _site_onceligi() -> List[str]:
        try:
            from cekirdek import yapilandirma
            return list(yapilandirma.yukle().get("arama", {})
                        .get("site_onceligi", []))
        except Exception:
            return []

    def topla(self, metin: str, detayli: bool = False,
              adet: int = 6, zorla_birim: str = "",
              gorev_filtre: List[str] | None = None) -> Dict[str, object]:
        kategori = kategori_belirle(metin)
        secili = list(KATEGORI_BIRIMLER.get(kategori, ["web_birimi"]))
        if zorla_birim and zorla_birim in self._birimler:
            secili = [zorla_birim]      # ör: haber turunda yalnız RSS birimi
        # Güncel veri birimi (hava/döviz) artık her aramada DENENİR: eşleşme
        # yoksa boş döner, maliyet ihmal edilebilir. Ayarla kapatılabilir.
        if "guncel_veri_birimi" not in secili and self._guncel_veri_acik():
            secili.append("guncel_veri_birimi")
        gorev = {"sorgu": metin, "adet": adet, "kategori": kategori,
                 "detayli": detayli,
                 "site_onceligi": self._site_onceligi(),
                 "filtre_url_icindekiler": gorev_filtre or [],
                 "web_ara": self._birimler["web_birimi"].ara}
        tum: List[Dict] = []
        hata_bilgileri: List[str] = []
        with ThreadPoolExecutor(max_workers=4) as havuz:
            gelecekte = {havuz.submit(self._birimler[a].ara, dict(gorev)): a
                         for a in secili if a in self._birimler}
            for f in as_completed(gelecekte, timeout=90):
                try:
                    tum += f.result() or []
                except Exception as e:
                    hata_bilgileri.append(f"{gelecekte[f]}: {str(e)[:120]}")
        # çok dilli aramada mükerrerleri ayıkla
        gorulen, temiz = set(), []
        for s in tum:
            anahtar = re.sub(r"[?#].*$", "", (s.get("url") or "").lower().rstrip("/"))
            if anahtar and anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            temiz.append(s)
        # güven + dil zenginliği sıralaması
        temiz.sort(key=lambda s: -(s.get("guvenilirlik", 0.5)))
        return {"kategori": kategori, "birimler": secili, "detayli": detayli,
                "sonuclar": temiz[: adet * 3], "hatalar": hata_bilgileri}

    def kanit_dosyasi(self, veri: Dict[str, object]) -> str:
        """Modele verilecek yapılandırılmış kanıt dosyası (zorunlu alanlarla)."""
        satirlar = [f"KATEGORI: {veri['kategori']} | BİRİMLER: "
                    f"{', '.join(veri['birimler'])} | DETAYLI: {veri['detayli']}"]
        for i, s in enumerate(veri["sonuclar"], 1):
            satirlar.append(
                f"{i}. [{s['kaynak_birimi']}] {s['baslik']} (güven:{s['guvenilirlik']}"
                f"{', tarih:' + s['guncellik'] if s.get('guncellik') else ''}"
                f"{', dil:' + s['dil'] if s.get('dil') else ''})\n"
                f"   {s['url']}\n   {s['ozet'][:260]}"
                + (f"\n   NOT: {s['notlar']}" if s.get("notlar") else ""))
        if veri.get("hatalar"):
            satirlar.append("ERMİŞİLEMEYEN: " + "; ".join(veri["hatalar"]))
        return "\n".join(satirlar)


DERLEME_SISTEM = (
    "Sen Arama Kurulu'nun derleyicisisin. Sana gelen KANIT DOSYASINI kullanarak "
    "kullanıcının sorusunu yanıtla. Zorunlu kurallar:\n"
    "1) Her önemli iddianın sonuna [kaynak no] atıf koy.\n"
    "2) Yanıtın sonunda şunları AYRI başlıklarla ver: 'Kaynak güveni', "
    "'Güncellik' (hangi bilgi ne zaman kontrol edildi), 'Belirsizlikler' "
    "(eksik/çelişkili neler), 'Gerekçe' (neden bu sonuç).\n"
    "3) Puan verirsen gerekçesini de yaz; puan kanıtın yerine geçmez.\n"
    "4) Kültürel/dinî karşılaştırma isteği varsa perspektifleri AYRI AYRI sun, "
    "bir geleneğin kendi görüşü ile akademik bulguyu karıştırma; alıntıyı mümkünse "
    "orijinal dilinde ver ve çevirisini yanında göster.\n"
    "5) Çok dilli kanıt varsa mükerrer bilgileri tekilleştir, çelişkileri belirt.\n"
    "6) Türkçe yanıt ver; madalyon gibi dolgu cümle yazma.\n"
    "7) SAYISAL/GÜNCEL VERİ (kur, hava, fiyat): yalnızca KANIT DOSYASINDAKi "
    "yapılandırılmış değerleri kullan — kendi bilginle tahmin yapma. Her sayının "
    "yanına kaynak adını ve zaman damgasını yaz (ör. '34,21 TL — exchangerate.host, "
    "2026-10-14 15:03'). Kanıt dosyasında yoksa 'bu veriye ulaşamadım' de.\n"
    "8) Ürün karşılaştırması: aynı model kodunu birebir eşleştir; farklı varyant "
    "(renk/depolu/uzatılmış pil vb.) satılarını AYRI göster, asla tek ürün gibi "
    "karıştırma. 'model-kodu-yok' etiketli kaynakları güvenilmez say. Fiyat "
    "bandı istendiyse band dışındaki ürünleri önerme; satıcılar arası büyük fiyat "
    "farkı varsa bunu 'Belirsizlikler'de açıkla.\n"
    "9) HABER/BAŞLIK: her haberi YAYIN TARİHİYLE ver; RSS kanıtındaki 'YAYIN:' "
    "damgasını aynen kullan. Tarih belirsizse 'tarih doğrulanamadı' yaz; bayat "
    "haberi güncel gibi SUNMA.\n"
    "10) ÜRÜN İNCELEME/PARALAK: sayfanın içindeki PUAN ve yorum örneklerini esas "
    "al. 1-10 puan ver ve her puana GEREKÇE yaz (kalite/fiyat-kullanıcı yorumu). "
    "Kullanıcı tercihleri/belleği geldiyse öneriyi ONA göre şekillendir ve hangi "
    "tercihin etkili olduğunu belirt.\n"
    "11) LİNK ZORUNLU: ürün/öneri yanıtında HER ürünün altında gerçek, kanıt "
    "dosyasından alınmış tam URL satırı ver ('Satın alma linki: https://...'). "
    "Kanıt dosyasında olmayan URL/FİYAT ASLA UYDURMA — link yoksa "
    "'link bulunamadı' yaz. Fiyatı kanıtta geçen değerin üstünde/altında "
    "gösterme; kullanıcı bütçe bandının üstündeyse 'bütçe üstü' etiketle.\n"
    "12) TABLO DÜZENİ: karşılaştırma tablosunu en fazla 4 sütun kur "
    "(Model | Fiyat | Öne çıkan özellik | Puan/10); uzun metin sütunu açma, "
    "ayrıntıyı tablo altına madde madde yaz; hücre içine link koyman "
    "gerekirse kısa ad + parantezde tam URL kullan.")
