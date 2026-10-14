# -*- coding: utf-8 -*-
"""GÖNDERİCİ — Mesajı uçtan uca işler.

Akış:
  kullanıcı mesajı → KARAR MERKEZİ (ağırlık + modül) → gerekiyorsa YETENEK çağrısı
  → hafızadan bağlam topla → seçili modele gönder → yanıtı hafızaya yaz → döndür.

Ayrıca "modülü çağır/sök/kur" gibi doğrudan sistem komutlarını tanır.
"""
from __future__ import annotations

import re
import threading
import uuid
from typing import Dict, Optional

from cekirdek import yapilandirma
from cekirdek.karar_merkezi import KararMerkezi
from cekirdek.modul_iskeleti import TEKIL, TUR_ORGAN, TUR_YETENEK
from cekirdek.ollama_kontrol import OllamaIstemcisi
from organlar.hafiza.modul import HafizaOrgan

# Organ nesnelerinin modül yükleyiciyle paylaşımı (tak-sök uyumlu tek örnek)
GONDERCI_BAGI = {"hafiza": None}

SISTEM_TABAN = (
    "Sen yerel, modüler bir yapay zekâ asistanısın. Türkçe konuş. "
    "Kullanıcının verdiği görevi eksiksiz ve doğrudan yap; dolgu cümle yazma. "
    "Kod istenirse tam ve çalışır kod ver."
)


class GorevGonderici:
    def __init__(self):
        self.ayar = yapilandirma.yukle()
        adres = self.ayar["ollama"]["adres"]
        self.ollama = OllamaIstemcisi(adres)
        self.hafiza = HafizaOrgan(self.ollama)
        GONDERCI_BAGI["hafiza"] = self.hafiza
        self.karar = KararMerkezi(self.ollama, lambda: TEKIL.sozluk)
        self.aktif_oturum: str = "genel"
        # onay bekleyen arka plan işlerinin sonuçları (oturum -> [iz])
        self._sonuclar: Dict[str, list] = {}
        self._kilit = threading.RLock()
        # Ollama tek model kilidi: aynı anda iki üretim gönderilmez (RAM/VRAM
        # şişmesinin ve "read timed out" kilitlenmelerinin ana nedeni buydu).
        self._uretim_kilit = threading.Lock()

    # ---------- başlatma ----------
    def baslat(self):
        TEKIL.tara()
        TEKIL.organlari_baslat()  # hafıza organı GONDERCI_BAGI üzerinden bağlanır

    # ---------- oturumlar ----------
    def yeni_oturum(self, ad: str = "") -> str:
        oid = uuid.uuid4().hex[:10]
        return oid

    # ---------- bekleyen sonuçları toplama (panel bunu yoklar) ----------
    def sonuclari_al(self, oturum: str) -> list:
        with self._kilit:
            return self._sonuclar.pop(oturum, [])

    def _sonuc_birak(self, oid: str, iz: dict):
        with self._kilit:
            self._sonuclar.setdefault(oid, []).append(iz)

    # ---------- ana akış ----------
    def isle(self, metin: str, oturum: Optional[str] = None,
             zorla_model: str = "", zorla_modul: str = "") -> Dict[str, object]:
        oid = oturum or self.aktif_oturum
        self.aktif_oturum = oid

        # Sistem komutları: /modul ara ... , /organ hafiza ... → arka plan/onay yolu
        m = self.komut_mu(metin)
        if m and not zorla_modul:
            tur, kod, girdi = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
            if kod in TEKIL.sozluk:
                karar = {"kaynak": "komut", "modul": kod, "agirlik": 0.5,
                         "model_secimi": "", "modul_girdisi": girdi or metin}
                return self._modul_yol(kod, girdi or metin, oid, karar,
                                       zorla_model, iz={"karar": karar, "adimlar": []})
        karar = self.karar.karar_ver(metin, oid)
        if zorla_modul:
            karar["modul"] = zorla_modul
            karar["modul_girdisi"] = metin
        iz = {"karar": karar, "adimlar": []}

        modul_adi = karar.get("modul", "yok")
        ek_bilgi = ""
        if modul_adi == "hafiza_ara":
            bulunan = self.hafiza.ara(karar.get("modul_girdisi", metin), oid)
            ek_bilgi = "\n".join(bulunan)
            iz["adimlar"].append({"adim": "hafıza sorgusu", "sonuc": ek_bilgi[:400]})
        elif modul_adi and modul_adi != "yok":
            girdi = karar.get("modul_girdisi", metin)
            return self._modul_yol(modul_adi, girdi, oid, karar, zorla_model, iz)

        return self._model_gonder(metin, oid, iz, ek_bilgi, modul_adi,
                                  karar, zorla_model)

    # ---------- modül çağrı yolu (onay/arka plan mantığı burada) ----------
    def _modul_yol(self, modul_adi: str, girdi: str, oid: str,
                   karar: dict, zorla_model: str, iz: dict) -> dict:
        # Araştırmacı Kurulu: tarama uzun sürebilir + dış dünya ONAYI gerekir
        # → daima arka planda işlenir; sonuç /api/sonuclar_bekleyen ile döner.
        if modul_adi == "arastirmaci":
            threading.Thread(target=self._arka_plan_isle,
                             args=(girdi, oid, karar, zorla_model),
                             daemon=True).start()
            return {"onay_bekliyor": True, "arkaplan": True, "oturum": oid,
                    "yanit": f"'{modul_adi}' kurulu taramaya başladı; "
                             "dış dünya erişimi için onay kartı çıkabilir. "
                             "Kanıt toplanınca ağır model derleyecek ve "
                             "sonuç sohbete düşecek…",
                    "karar": karar, "adimlar": [], "model": "", "hata": ""}
        # EL gibi yetenekler ONAY BEKLETEBİLİR → uzun süreli iş parçacığına
        # alınır; panel /api/onaylar ile kartı gösterir, karar gelince devam
        # edilir ve sonuç /api/sonuclar_bekleyen ile sohbete düşer.
        izin_istenen = (modul_adi == "el" and ("hedef" in str(girdi)
                        or "/" in str(girdi)))
        if izin_istenen:
            threading.Thread(target=self._arka_plan_isle,
                             args=(girdi, oid, karar, zorla_model),
                             daemon=True).start()
            return {"onay_bekliyor": True, "oturum": oid,
                    "yanit": f"'{modul_adi}' işlemi için onay bekleniyor… "
                             "Yukarıdaki karttan karar ver.",
                    "karar": karar, "adimlar": [], "model": "", "hata": ""}
        sonuc = TEKIL.modulu_calistir(modul_adi, girdi)
        if sonuc.get("basarili"):
            ek_bilgi = sonuc.get("yanit", "")
            iz["adimlar"].append({"adim": f"yetenek: {modul_adi}",
                                  "sonuc": ek_bilgi[:400]})
        else:
            iz["adimlar"].append({"adim": f"yetenek: {modul_adi}",
                                  "hata": sonuc.get("hata", "")})
        return self._model_gonder(girdi, oid, iz, ek_bilgi, modul_adi,
                                  karar, zorla_model)

    # ---------- arka planda (onay bekleyen) iş ----------
    def _arka_plan_isle(self, metin: str, oid: str, karar: dict,
                        zorla_model: str):
        modul_adi = karar.get("modul", "yok")
        girdi = karar.get("modul_girdisi", metin)
        iz = {"karar": karar, "adimlar": [{"adim": f"yetenek: {modul_adi}",
                                           "sonuc": "onaylandı"}]}
        sonuc = TEKIL.modulu_calistir(modul_adi, girdi)
        if sonuc.get("basarili"):
            ek_bilgi = sonuc.get("yanit", "")
            iz["adimlar"].append({"adim": f"{modul_adi} sonucu",
                                  "sonuc": ek_bilgi[:400]})
        else:
            ek_bilgi = ""
            iz["adimlar"].append({"adim": f"{modul_adi} sonucu",
                                  "hata": sonuc.get("hata", sonuc.get("yanit", ""))})
        tam = self._model_gonder(metin, oid, iz, ek_bilgi, modul_adi,
                                 karar, zorla_model)
        self._sonuc_birak(oid, tam)

    # ---------- ortak model gönderimi ----------
    def _model_gonder(self, metin: str, oid: str, iz: dict, ek_bilgi: str,
                      modul_adi: str, karar: dict, zorla_model: str) -> dict:
        # hafızadan bağla
        self.hafiza.kaydet(oid, "user", metin)
        baglam = self.hafiza.baglam(oid)

        model = zorla_model or karar.get("model_secimi") or \
            self.ayar["modeller"].get("rutin_model")
        if modul_adi == "arastirmaci" and not zorla_model:
            # kanıt dosyasını derlemek AĞIR iş → ağır modeli zorla
            agir = self.ayar["modeller"].get("agir_model")
            if agir:
                model = agir
        sistem = SISTEM_TABAN
        if modul_adi == "arastirmaci":
            try:
                from kurul import DERLEME_SISTEM as _ds
                sistem = _ds
            except Exception:
                pass
        parcalar = [sistem]
        if baglam.get("kalici_bellek"):
            parcalar.append("KALICI BELLEK (kullanıcı hakkında):\n"
                            + baglam["kalici_bellek"])
        if baglam.get("oturum_ozeti"):
            parcalar.append("BU OTURUMUN ÇALIŞMA NOTU:\n" + baglam["oturum_ozeti"])
        if ek_bilgi:
            parcalar.append(f"MODÜLDEN GELEN VERİ ({modul_adi}):\n{ek_bilgi}")
        sistem_metni = "\n\n---\n\n".join(parcalar)

        yanit, hata = "", ""
        if not model:
            hata = ("Model seçilmemiş. Ayarlar panelinden rutin/ağır modelleri "
                    "seçin (Ollama'da yüklü olanlardan).")
        elif not self.ollama.canli_mi():
            hata = "Ollama sunucusuna ulaşılamıyor. Başlatılmış olmalı."
        else:
            # Ağır işaretleme (arama kurulu / görsel) varsa timeout uzatılır;
            # ayrıca ayarlardan "uretim_zaman_asimi" ile elle de ayarlanabilir.
            zaman_asimi = int(self.ayar.get("modeller", {})
                              .get("uretim_zaman_asimi", 0)) or \
                (900 if (modul_adi == "arastirmaci" or ek_bilgi.startswith("GÖRSEL"))
                 else 300)
            denemeler = [model]
            rutin = self.ayar["modeller"].get("rutin_model") or ""
            if rutin and rutin != model:
                denemeler.append(rutin)   # ağır model kilitliyse sohbet ölmesin
            for m in denemeler:
                try:
                    with self._uretim_kilit:   # sıraya al: tek istek, tek model
                        yanit = self.ollama.uretim(m, baglam["mesajlar"],
                                                   sistem=sistem_metni,
                                                   zaman_asimi=zaman_asimi)
                    if yanit:
                        model = m
                        break
                except Exception as e:
                    hata = f"Üretim hatası ({m}): {str(e)[:200]}"
                    if m != model:
                        hata += " — yedek model de denendi."

        if yanit:
            self.hafiza.kaydet(oid, "assistant", yanit,
                               {"model": model, "agirlik": karar.get("agirlik")})
        iz.update({"yanit": yanit, "hata": hata, "model": model, "oturum": oid})
        return iz

    # ---------- sistem komutları (sohbette hızlı yol) ----------
    KOMUT_DESEN = re.compile(r"^/(modul|yetenek|organ)\s+(\S+)\s*(.*)$", re.I)

    def komut_mu(self, metin: str):
        return self.KOMUT_DESEN.match(metin.strip())
