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

    def _model_hazirla(self, model: str, bekleme_sn: int = 1800) -> None:
        """27B gibi büyük GGUF modeller diskten RAM/VRAM'e yüklenirken Ollama
        ilk istekte dakikalarca sessiz kalabilir; bu 'ısındırma' çağrısıdır.
        Başarısız olursa sessizce geçilir (asıl üretim yine deneyecek)."""
        try:
            requests.post(self.adres + "/api/generate",
                          json={"model": model, "prompt": "",
                                "keep_alive": bekleme_sn, "stream": False},
                          timeout=(10, max(300, bekleme_sn - 60)))
        except Exception:
            pass

    def uretim(self, model: str, mesajlar: List[Dict[str, str]],
               sistem: str = "", sıcaklik: float = 0.4,
               zaman_asimi: int = ZAMAN_ASIMI,
               gorseller: List[str] | None = None,
               ısındır: bool = True) -> str:
        """Mesaj üretimi. gorseller: base64 string listesi — Ollama çok-modal
        (llava/qwen-vision vb.) modellerde son kullanıcı mesajına eklenir.
        Metin-only model verirse Ollama görseli yok sayar; hata olmaz.

        stream=True: token akışıyla okuma boşlukları hiç oluşmaz → büyük
        model yükleme/üretim sürelerinde 'read timed out' ölümlerini kökten
        keser. Parçalar toplanıp tek metin olarak döner (sözleşme değişmedi).
        kesinti: 30 sn içinde ilk token gelmezse bağlantı yenilenir (model
        gerçekten çalışıyorsa token akar, kesinti olmaz)."""
        if ısındır:
            self._model_hazirla(model)
        payload = {
            "model": model,
            "messages": mesajlar,
            "stream": True,
            "keep_alive": "30m",
            "options": {"temperature": sıcaklik},
        }
        if sistem:
            payload["system"] = sistem
        if gorseller and mesajlar:
            payload["messages"][-1]["images"] = list(gorseller)
        import socket
        son_metin, deneme = "", 0
        while True:
            deneme += 1
            parcalar: List[str] = []
            try:
                with requests.post(self.adres + "/api/chat", json=payload,
                                   timeout=(30, zaman_asimi), stream=True) as r:
                    r.raise_for_status()
                    for satir in r.iter_lines():
                        if not satir:
                            continue
                        import json as _j
                        try:
                            veri = _j.loads(satir.decode("utf-8"))
                        except Exception:
                            continue
                        if veri.get("error"):
                            raise RuntimeError(veri["error"])
                        parca = (veri.get("message") or {}).get("content", "")
                        if parca:
                            parcalar.append(parca)
                return "".join(parcalar).strip()
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError,
                    socket.timeout) as e:
                # token akmaya başladıysa kısmi metni koru; akış hiç başlamadıysa
                # taze istekle yeniden dene (Ollama'nın sessiz bağlantı kesmesi)
                if parcalar or deneme >= 2:
                    return "".join(parcalar).strip()
                continue
            except requests.exceptions.ReadTimeout:
                # okuma boşluğu tek seferlik olduysa: toplananı döndür ya da bir kez daha
                return "".join(parcalar).strip()

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
