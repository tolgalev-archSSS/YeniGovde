# -*- coding: utf-8 -*-
"""Ollama sunucusuyla konuşan katman: model tarama, durum, çalışma testi."""
from __future__ import annotations

import time
from typing import Dict, List

import requests

# NOT: Bu süre bekleme (idle) zaman aşımıdır, toplam süre değil. Büyük modellerde
# model yükleme + uzun kanıt dosyası derlemesi 120 sn'yi rahatça aşar → 900 sn.
ZAMAN_ASIMI = 900


class OllamaIstemcisi:
    def __init__(self, adres: str):
        self.adres = adres.rstrip("/")

    def surumu_al(self) -> str:
        r = requests.get(self.adres + "/api/version", timeout=5)
        r.raise_for_status()
        return r.json().get("version", "?")

    def modelleri_tara(self) -> List[Dict[str, object]]:
        """Yüklü lokal modelleri boyut/bağlam bilgisiyle döndürür."""
        r = requests.get(self.adres + "/api/tags", timeout=10)
        r.raise_for_status()
        liste = []
        for m in r.json().get("models", []):
            boyut = m.get("size", 0) or 0
            liste.append(
                {
                    "ad": m.get("name", ""),
                    "boyut_gb": round(boyut / (1024**3), 2),
                    "parametre": (m.get("details", {}) or {}).get("parameter_size", "?"),
                    "baglam": (m.get("details", {}) or {}).get("context_length", 0),
                    "soyut": m.get("model", m.get("name", "")),
                }
            )
        return liste

    def canli_mi(self) -> bool:
        try:
            self.surumu_al()
            return True
        except Exception:
            return False

    def uretim(self, model: str, mesajlar: List[Dict[str, str]],
               sistem: str = "", sıcaklik: float = 0.4,
               zaman_asimi: int = ZAMAN_ASIMI,
               gorseller: List[str] | None = None) -> str:
        """Mesaj üretimi. gorseller: base64 string listesi — Ollama çok-modal
        (llava/qwen-vision vb.) modellerde son kullanıcı mesajına eklenir.
        Metin-only model verirse Ollama görseli yok sayar; hata olmaz."""
        payload = {
            "model": model,
            "messages": mesajlar,
            "stream": False,
            "options": {"temperature": sıcaklik},
        }
        if sistem:
            payload["system"] = sistem
        if gorseller and mesajlar:
            payload["messages"][-1]["images"] = list(gorseller)
        r = requests.post(self.adres + "/api/chat", json=payload, timeout=zaman_asimi)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()

    def sayisal_test(self, model: str) -> Dict[str, object]:
        """Model gerçekten yanıt verebiliyor mu? Kısa deneme üretimi."""
        bas = time.time()
        try:
            cevap = self.uretim(
                model,
                [{"role": "user", "content": "Sadece OK yaz."}],
                sistem="Yalnızca istenen kelimeyi yaz.",
                sıcaklik=0.0,
                zaman_asimi=90,
            )
            return {"basarili": bool(cevap), "sure_sn": round(time.time() - bas, 1),
                    "ornek": cevap[:60], "hata": ""}
        except Exception as e:
            return {"basarili": False, "sure_sn": round(time.time() - bas, 1),
                    "ornek": "", "hata": str(e)[:200]}
