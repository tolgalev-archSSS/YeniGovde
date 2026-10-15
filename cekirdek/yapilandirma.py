# -*- coding: utf-8 -*-
"""TÜM SİSTEM AYARLARINI YÖNETEN KATMAN.

Ayarlar tek bir yerde tutulur: `ayarlar/ayarlar.json`.
İlk kurulumda eksik alanlar varsayılanlarla doldurulur (otomatik kontrol).
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

KOK_DIZIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_DIZIN = os.path.join(KOK_DIZIN, "ayarlar")
AYAR_DOSYA = os.path.join(AYAR_DIZIN, "ayarlar.json")
VERI_DIZIN = os.path.join(KOK_DIZIN, "veri")
LOG_DIZIN = os.path.join(VERI_DIZIN, "gunlukler")
SOHBET_DIZIN = os.path.join(VERI_DIZIN, "sohbetler")
HAFIZA_DIZIN = os.path.join(VERI_DIZIN, "hafiza")
MODUL_DIZIN = os.path.join(KOK_DIZIN, "moduller")
ORGAN_DIZIN = os.path.join(KOK_DIZIN, "organlar")
YETENEK_DIZIN = os.path.join(KOK_DIZIN, "yetenekler")
# Node yönetimi: yüklü node'lar ayrı klasörde; dışarıdan yazılanlar KABUL'da
NODE_DIZIN = os.path.join(KOK_DIZIN, "nodeller")
KABUL_DIZIN = os.path.join(NODE_DIZIN, "kabul")
SOKULEN_DIZIN = os.path.join(NODE_DIZIN, "sokulen")

VARSAYILAN_AYARLAR: Dict[str, Any] = {
    "sunucu": {"ip": "127.0.0.1", "port": 8765},
    "ollama": {"adres": "http://127.0.0.1:11434"},
    "modeller": {
        "rutin_model": "",       # hafif model: sohbet / sıradan işler
        "agir_model": "",        # ağır model: kodlama / planlama / analiz
        "siniflandirma_modeli": "",  # karar merkezi için küçük LLM
        "guc_orani": 0.55,       # eşikten yüksek ağırlıkta ağır modele geçilir
    },
    "organlar": {},              # organ adı -> True/False (sürekli aktif)
    "yetenekler": {},            # yetenek adı -> True/False (kurulu mu)
    "arama": {
        "onay_serbest": False,   # True → dış dünya işlemleri onaysız yapılır
        "ingilizce_ara": True,   # TR sorgunun yanında İngilizce de tara
        "guncel_veri_birimi_acik": True,  # hava/döviz birimi her aramada denensin mi?
        "site_onceligi": ["hepsiburada.com", "trendyol.com", "akakce.com",
                          "cimri.com"],   # ürün aramasında önce listelenecek TR siteleri
        "varsayilan_adet": 6,
    },
    "hafiza": {
        "etkin": True,
        "motor": "yerel",        # yerel | mem0
        "pencere_mesaj": 12,     # modele taşınan son mesaj sayısı
        "oturum_basina_ozet": 8, # kaç mesajda bir arka plan özeti alınsın
        "mem0_dosya": "veri/hafiza/mem0_hafiza.json",
    },
}

_KILIT = threading.RLock()


def _derin_baglas(varsayilan: Dict[str, Any], gelen: Dict[str, Any]) -> Dict[str, Any]:
    """Eksik anahtarları varsayılanlarla doldurur; kullanıcı değerlerini korur."""
    sonuc = dict(varsayilan)
    for k, v in gelen.items():
        if isinstance(v, dict) and isinstance(sonuc.get(k), dict):
            sonuc[k] = _derin_baglas(sonuc[k], v)
        else:
            sonuc[k] = v
    return sonuc


def yukle() -> Dict[str, Any]:
    with _KILIT:
        if not os.path.exists(AYAR_DOSYA):
            kaydet(dict(VARSAYILAN_AYARLAR))
            return dict(VARSAYILAN_AYARLAR)
        try:
            with open(AYAR_DOSYA, "r", encoding="utf-8") as f:
                veri = json.load(f)
        except Exception:
            veri = {}
        birlesik = _derin_baglas(VARSAYILAN_AYARLAR, veri)
        if birlesik != veri:
            kaydet(birlesik)
        return birlesik


def kaydet(aynar: Dict[str, Any]) -> None:
    with _KILIT:
        os.makedirs(AYAR_DIZIN, exist_ok=True)
        tmp = AYAR_DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(aynar, f, ensure_ascii=False, indent=2)
        os.replace(tmp, AYAR_DOSYA)


def guncelle(guncel: Dict[str, Any]) -> Dict[str, Any]:
    """Kısmi güncelleme: {'modeller': {'rutin_model': 'llama3.2'}} gibi."""
    with _KILIT:
        ayarlar = yukle()
        ayarlar = _derin_baglas(ayarlar, guncel)
        kaydet(ayarlar)
        return ayarlar


def gerekli_dizinler():
    for d in (AYAR_DIZIN, VERI_DIZIN, LOG_DIZIN, SOHBET_DIZIN, HAFIZA_DIZIN,
              NODE_DIZIN, KABUL_DIZIN, SOKULEN_DIZIN):
        os.makedirs(d, exist_ok=True)
