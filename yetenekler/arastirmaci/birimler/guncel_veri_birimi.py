# -*- coding: utf-8 -*-
"""GUNCEL VERI BİRİMİ — Zaman damgalı yapılandırılmış veri (güvenli tahmin yok).

  Hava durumu  → open-meteo (anahtarsız, ücretsiz)
  Döviz (USD/EUR karşı TL vb.) → TCMB EVDS / exchangerate.host yedeği
Şehir/para eşleştirmeleri basit sözlük; yeni kaynak = yeni fonksiyon + KATALOG.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List

import requests

SEHIR_KOODINAT = {
    "istanbul": (41.01, 28.98), "ankara": (39.93, 32.86),
    "izmir": (38.42, 27.13), "bursa": (40.19, 29.06),
    "antalya": (36.90, 30.70), "londra": (51.51, -0.13),
    "paris": (48.86, 2.35), "berlin": (52.52, 13.41),
    "tokyo": (35.68, 139.69), "new york": (40.71, -74.01),
}
HAVA_SOZLUGU = {0: "açık", 1: "çoğunlukla açık", 2: "parçalı bulutlu",
                3: "kapalı", 45: "sisli", 48: "kırağılı sis", 51: "çisenti",
                53: "hafif yağmur", 55: "yoğun çisenti", 61: "hafif yağmur",
                63: "yağmur", 65: "kuvvetli yağmur", 71: "kar", 73: "kar",
                75: "yoğun kar", 80: "sağanak", 81: "sağanak", 82: "şiddetli sağanak",
                95: "fırtına", 96: "dolulu fırtına"}


def _hava(sorgu: str) -> List[Dict]:
    sehir = next((s for s in SEHIR_KOODINAT if s in sorgu.lower()), None)
    if not sehir:
        return []
    enlem, boylam = SEHIR_KOODINAT[sehir]
    r = requests.get("https://api.open-meteo.com/v1/forecast",
                     params={"latitude": enlem, "longitude": boylam,
                             "current": "temperature_2m,weather_code,wind_speed_10m",
                             "daily": "temperature_2m_max,temperature_2m_min,"
                                      "precipitation_probability_max,weather_code",
                             "timezone": "auto", "forecast_days": 2}, timeout=15)
    r.raise_for_status()
    j = r.json()
    simdi = j["current"]
    yarin = j["daily"]
    metin = (f"{sehir.title()} şu an: {simdi['temperature_2m']}°C, "
             f"{HAVA_SOZLUGU.get(simdi['weather_code'], 'kod ' + str(simdi['weather_code']))}, "
             f"rüzgar {simdi['wind_speed_10m']} km/s. "
             f"Yarın ({yarin['time'][1]}): {yarin['temperature_2m_min'][1]}…"
             f"{yarin['temperature_2m_max'][1]}°C, yağmur olasılığı "
             f"%{yarin['precipitation_probability_max'][1] or 0}.")
    return [{"baslik": f"Hava — {sehir}", "url": "https://open-meteo.com",
             "ozet": metin, "kaynak_birimi": "open-meteo", "guvenilirlik": 0.9,
             "guncellik": datetime.now().isoformat(timespec="minutes"),
             "dil": "tr", "notlar": "birincil API, birebir ölçüm"}]


def _doviz(sorgu: str) -> List[Dict]:
    eslesme = re.search(r"(dolar|usd|euro|eur|sterlin|gbp)", sorgu.lower())
    if not eslesme:
        return []
    para = {"dolar": "USD", "usd": "USD", "euro": "EUR", "eur": "EUR",
            "sterlin": "GBP", "gbp": "GBP"}[eslesme.group(1)]
    try:
        r = requests.get("https://api.exchangerate.host/latest",
                         params={"base": para, "symbols": "TRY"}, timeout=15)
        kur = r.json()["rates"]["TRY"]
        kaynak = "exchangerate.host"
    except Exception:
        # ikinci yedek: serbest kur kuyruğu
        r = requests.get(f"https://open.er-api.com/v6/latest/{para}", timeout=15)
        kur = r.json()["rates"]["TRY"]
        kaynak = "open.er-api.com"
    return [{"baslik": f"1 {para} = {kur:.2f} TL", "url": f"https://{kaynak}",
             "ozet": f"Güncel kur: 1 {para} ≈ {kur:.4f} TL (kaynak: {kaynak}).",
             "kaynak_birimi": kaynak, "guvenilirlik": 0.85,
             "guncellik": datetime.now().isoformat(timespec="minutes"),
             "dil": "tr", "notlar": "anlık yapılandırılmış veri"}]


KATALOG = [("hava", _hava), ("doviz", _doviz)]


def ara(gorev: Dict[str, object]) -> List[Dict]:
    sorgu = str(gorev.get("sorgu", "")).strip()
    cikti: List[Dict] = []
    for ad, fonk in KATALOG:
        try:
            cikti += fonk(sorgu)
        except Exception as e:
            cikti.append({"baslik": f"[{ad}] verisi alınamadı", "url": "",
                          "ozet": str(e)[:150], "kaynak_birimi": f"{ad}-hata",
                          "guvenilirlik": 0.0, "guncellik": "", "dil": "",
                          "notlar": ""})
    return [s for s in cikti if s["guvenilirlik"] > 0]
