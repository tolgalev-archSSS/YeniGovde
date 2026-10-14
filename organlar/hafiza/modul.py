# -*- coding: utf-8 -*-
"""HAFIZA ORGANI — Oturum geçmişi, yarı kalıcı özetler ve uzun dönemli bellek.

İstek:
  • Sohbet harfi harfine hatırlanmak zorunda değil; "nerede kaldık, ne
    yapılacaktı, ne yaptık" bilinmeli, eski sohbete atıf yapılabilmeli,
    sürekli eski konular deşilmemeli.
  • Sistem arka planda kendine dosyalar yazar.
  • Motor olarak Mem0 önerildi; kuruluysa O kullanılır ("mem0"), değilse bu
    modülün kendi yerel motoru çalışır ("yerel").

Yerel motor (MotorYerel):
  - Ham kayıt        : veri/sohbetler/<oturum>.jsonl   (geçmiş defteri)
  - Oturum özeti     : veri/hafiza/oturum_<id>.md      (kısa çalışma notu)
  - Uzun dönem bellek: veri/hafiza/bellek.md           (kalıcı gerçekler)
  - Her N mesajda bir, arka plan thread'inde RUTİN modelle özetletilir.
  - Modele yalnızca güncel pencere + tek özet gider → eski konular taşınmaz.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Dict, List, Optional

from cekirdek import yapilandirma


class MotorYerel:
    """Dosya tabanlı, LLM destekli hafızacı."""

    def __init__(self, ollama=None):
        self.ollama = ollama
        self._kilit = threading.RLock()
        yapilandirma.gerekli_dizinler()

    # ----- oturum dosyaları -----
    def _oturum_yol(self, oid: str) -> str:
        return os.path.join(yapilandirma.SOHBET_DIZIN, f"{oid}.jsonl")

    def _ozet_yol(self, oid: str) -> str:
        return os.path.join(yapilandirma.HAFIZA_DIZIN, f"oturum_{oid}.md")

    @property
    def BELLEK_YOL(self) -> str:
        return os.path.join(yapilandirma.HAFIZA_DIZIN, "bellek.md")

    def mesaj_ekle(self, oid: str, rol: str, icerik: str, meta: Optional[dict] = None):
        with self._kilit:
            satir = {"zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "rol": rol, "icerik": icerik}
            if meta:
                satir["meta"] = meta
            with open(self._oturum_yol(oid), "a", encoding="utf-8") as f:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")

    def mesajlari_getir(self, oid: str) -> List[dict]:
        yol = self._oturum_yol(oid)
        if not os.path.exists(yol):
            return []
        with self._kilit, open(yol, "r", encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def ozet_oku(self, oid: str) -> str:
        yol = self._ozet_yol(oid)
        if os.path.exists(yol):
            with open(yol, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def ozet_yaz(self, oid: str, metin: str):
        with self._kilit, open(self._ozet_yol(oid), "w", encoding="utf-8") as f:
            f.write(metin.strip() + "\n")

    def bellek_oku(self) -> str:
        if os.path.exists(self.BELLEK_YOL):
            with open(self.BELLEK_YOL, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def bellek_ekle(self, satirlar: List[str]):
        satirlar = [s for s in (x.strip("-•* ").strip() for x in satirlar) if s]
        if not satirlar:
            return
        with self._kilit:
            var = self.bellek_oku()
            yeni = [s for s in satirlar if s not in var]
            if not yeni:
                return
            with open(self.BELLEK_YOL, "a", encoding="utf-8") as f:
                if var and not var.endswith("\n"):
                    f.write("\n")
                for s in yeni:
                    f.write(f"- {s}\n")

    # ----- özetleme -----
    OZET_SISTEM = (
        "Sen bir sistemin hafıza memurusun. Sana verilen konuşma bölümü için "
        "Türkçe, MADDELER HALİNDE çalışma notu yaz. Kural: kısa ama eksiksiz; "
        "şiirsel/dolgu cümle YASAK. Şu başlıkları kullan:\n"
        "## Yapıldı\n## Yarım kaldı / yapılacak\n## Kararlar ve önemli bilgiler\n"
        "## Kullanıcının bilinen tercihleri\n"
        "Yalnızca notları yaz, ön söz/son söz yazma."
    )

    def _metinden_temizle(self, cevap: str) -> str:
        return re.sub(r"^```.*?```", "", cevap, flags=re.S).strip()

    def oturumu_ozetle(self, oid: str, model: str) -> bool:
        msgs = self.mesajlari_getir(oid)
        if len(msgs) < 4 or not model or not self.ollama:
            return False
        eski_ozet = self.ozet_oku(oid)
        govde = "\n".join(f"{m['rol']}: {m['icerik'][:1200]}" for m in msgs[-30:])
        istem = (f"ÖNCEKİ NOT (güncelle, tekrara düşme):\n{eski_ozet or '(yok)'}\n\n"
                 f"YENİ KONUŞMA BÖLÜMÜ:\n{govde}")
        try:
            cevap = self.ollama.uretim(model, [{"role": "user", "content": istem}],
                                       sistem=self.OZET_SISTEM, sıcaklik=0.2,
                                       zaman_asimi=300)
            if cevap:
                self.ozet_yaz(oid, self._metinden_temizle(cevap))
                return True
        except Exception:
            pass
        return False

    BELLEK_CIKAR_SISTEM = (
        "Konuşmadan, ileride de geçerli olacak KALICI kullanıcı gerçeklerini çıkar "
        "(tercihler, isim/iş, sabit kararlar). Madde madde Türkçe yaz. Hiç yoksa "
        "yalnızca YOK yaz. Günlük sohbet ayrıntısını alma."
    )

    def kalici_bellek_cikar(self, oid: str, model: str) -> int:
        msgs = self.mesajlari_getir(oid)
        if not model or not self.ollama or len(msgs) < 6:
            return 0
        govde = "\n".join(f"{m['rol']}: {m['icerik'][:800]}" for m in msgs[-40:])
        try:
            cevap = self.ollama.uretim(model, [{"role": "user", "content": govde}],
                                       sistem=self.BELLEK_CIKAR_SISTEM, sıcaklik=0.1)
            cevap = self._metinden_temizle(cevap)
            if not cevap or cevap.upper().startswith("YOK"):
                return 0
            satirlar = [l for l in cevap.splitlines()
                        if l.strip().startswith(("-", "•", "*"))]
            self.bellek_ekle(satirlar)
            return len(satirlar)
        except Exception:
            return 0

    # ----- modele verilecek bağlam -----
    def baglam_kur(self, oid: str) -> Dict[str, object]:
        """Güncel pencere + oturum özeti + kalıcı bellek. Eski konular taşınmaz."""
        ayar = yapilandirma.yukle()["hafiza"]
        msgs = self.mesajlari_getir(oid)
        pencere = [{"role": m["rol"], "content": m["icerik"]}
                   for m in msgs[-int(ayar.get("pencere_mesaj", 12)):]]
        return {"mesajlar": pencere,
                "oturum_ozeti": self.ozet_oku(oid),
                "kalici_bellek": self.bellek_oku(),
                "toplam_mesaj": len(msgs)}


class MotorMem0:
    """Mem0 kancası — kuruluysa uzun dönem bellek Mem0'a devredilir.

    Kurulum: pip install mem0ai  →  ayarlarda hafiza.motor='mem0'.
    Embedding ve LLM, Mem0 ayarında Ollama'ya yönlendirilir; tamamen lokal kalır.
    """

    def __init__(self, ollama_adres: str, llm_model: str):
        self.hazir = False
        self._istemci = None
        try:
            from mem0 import Memory  # type: ignore
            self._Memory = Memory
            self.adres, self.llm_model = ollama_adres, llm_model
            self.hazir = True
        except Exception:
            self.hazir = False

    def girdi(self, rol: str, icerik: str, oid: str):
        if not self.hazir:
            return
        try:
            if self._istemci is None:
                self._istemci = self._Memory.from_config({
                    "llm": {"provider": "ollama",
                            "config": {"model": self.llm_model,
                                       "ollama_base_url": self.adres}},
                    "embedder": {"provider": "ollama",
                                 "config": {"model": "nomic-embed-text",
                                            "ollama_base_url": self.adres}},
                })
            self._istemci.add([{"role": "user" if rol == "user" else "assistant",
                                "content": icerik}], user_id=oid)
        except Exception:
            pass

    def ara(self, sorgu: str, oid: str, limit: int = 5) -> List[str]:
        if not self.hazir or self._istemci is None:
            return []
        try:
            r = self._istemci.search(sorgu, user_id=oid, limit=limit)
            return [x.get("memory", "") for x in r.get("results", [])]
        except Exception:
            return []


class HafizaOrgan:
    """Organ kabuğu: arka plan özetleme döngüsü + iki motor birden."""

    def __init__(self, ollama=None):
        self.ollama = ollama
        self.yerel = MotorYerel(ollama)
        self.mem0: Optional[MotorMem0] = None
        self._dur = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._son_sayac: Dict[str, int] = {}

    # ---- organ sözleşmesi ----
    def baslat(self):
        self._dur.clear()
        self._thread = threading.Thread(target=self._dongu, daemon=True,
                                        name="hafiza-organi")
        self._thread.start()

    def dur(self):
        self._dur.set()

    def calistir(self, metin: str, **saglama) -> dict:
        """Karar merkezi 'geçmişte ne vardı?' derse buradan arama yapılır."""
        return {"yanit": "\n".join(self.ara(metin, saglama.get("oturum", "")))
                or "Hafızada ilgili kayıt bulunamadı."}

    # ---- arka plan döngüsü ----
    def _motor_sec(self) -> str:
        return yapilandirma.yukle()["hafiza"].get("motor", "yerel")

    def _dongu(self):
        """Her 20 sn: eşiği aşan oturumları rutin modelle arka planda özetle."""
        while not self._dur.wait(20):
            try:
                ayar = yapilandirma.yukle()
                haf = ayar["hafiza"]
                if not haf.get("etkin", True):
                    continue
                model = (ayar["modeller"].get("siniflandirma_modeli")
                         or ayar["modeller"].get("rutin_model"))
                esik = int(haf.get("oturum_basina_ozet", 8))
                for dosya in os.listdir(yapilandirma.SOHBET_DIZIN):
                    if not dosya.endswith(".jsonl"):
                        continue
                    oid = dosya[:-6]
                    n = len(self.yerel.mesajlari_getir(oid))
                    if n >= esik and n - self._son_sayac.get(oid, 0) >= esik:
                        self._son_sayac[oid] = n
                        self.yerel.oturumu_ozetle(oid, model)
                        self.yerel.kalici_bellek_cikar(oid, model)
            except Exception:
                continue

    # ---- dış arayüz ----
    def kaydet(self, oid: str, rol: str, icerik: str, meta=None):
        self.yerel.mesaj_ekle(oid, rol, icerik, meta)
        if self._motor_sec() == "mem0":
            if self.mem0 is None:
                a = yapilandirma.yukle()
                self.mem0 = MotorMem0(a["ollama"]["adres"], a["modeller"]["rutin_model"])
            self.mem0.girdi(rol, icerik, oid)

    def baglam(self, oid: str) -> Dict[str, object]:
        return self.yerel.baglam_kur(oid)

    def ara(self, sorgu: str, oid: str = "") -> List[str]:
        """Mem0 varsa oradan; yoksa bellek.md + oturum özetlerinde metin araması."""
        if self.mem0 and self.mem0.hazir:
            r = self.mem0.ara(sorgu, oid or "varsayilan")
            if r:
                return r
        sonuc, kelimeler = [], [w for w in re.split(r"\W+", sorgu.lower()) if len(w) > 3]
        for blok in self.yerel.bellek_oku().splitlines() + self._tum_ozetler():
            low = blok.lower()
            if any(w in low for w in kelimeler):
                sonuc.append(blok.strip())
        return sonuc[:8]

    def _tum_ozetler(self) -> List[str]:
        satirlar = []
        for f in os.listdir(yapilandirma.HAFIZA_DIZIN):
            if f.startswith("oturum_") and f.endswith(".md"):
                with open(os.path.join(yapilandirma.HAFIZA_DIZIN, f), encoding="utf-8") as fh:
                    satirlar.extend(fh.read().splitlines())
        return satirlar

    def kalici_ekle(self, yeni_satirlar):
        if isinstance(yeni_satirlar, str):
            yeni_satirlar = [yeni_satirlar]
        if yeni_satirlar:
            self.yerel.bellek_ekle(list(yeni_satirlar))


# Modül yükleyicinin beklediği sözleşme sözlüğü (organ olarak kayıt).
sozlesme = {
    "kod": "hafiza",
    "ad": "Hafıza (Hipokampüs)",
    "tur": "organ",
    "surum": "0.1",
    "aciklama": "Oturumları kaydeder, arka planda özetler, kalıcı bellek tutar.",
    "gorev_anahtarlari": ["hatırla", "geçmiş", "önceki", "ne yapmıştık", "bellek"],
    "_organ_nesnesi": None,  # sunucu başlatınca atanır (HafizaOrgan örneği)
}


def _baslat():
    org = sozlesme["_organ_nesnesi"]
    if org:
        org.baslat()


def _dur():
    org = sozlesme["_organ_nesnesi"]
    if org:
        org.dur()


def _calistir(metin: str, **saglama):
    org = sozlesme["_organ_nesnesi"]
    if not org:
        return "Hafıza organı henüz hazır değil."
    return org.calistir(metin, **saglama)


sozlesme.update({"baslat": _baslat, "dur": _dur, "calistir": _calistir})
