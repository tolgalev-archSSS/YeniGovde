# -*- coding: utf-8 -*-
"""EL YETENEĞİ — Bilgisayarı kullanmanın kolu: dosya ve program işleri.

Gerektiğinde karar merkezi tarafından çağrılır; sürekli çalışmaz.
Karar merkezi bu yeteneğe şu JSON'u gönderir (modul_girdisi):
  {"eylem": "dosya_yaz", "hedef": "~/notlar.txt", "icerik": "...", ...}
Ayrıca düz metin de kabul eder: basit komut sözdizimi aşağıdadır
  /el oku <yol> | yaz <yol> || içerik | sil <yol> | listele <yol>
      ac <program> | kapat <ad> | surecler [sorgu] | duzelt <yol>||eski||yeni

ONAY AKIŞI: tehlikeli eylemlerde kapıcı onay kartı üretir; istek AYNI SOHBET
MESAJI içinde bekler (gonderci mesajı iplikte işler, panel bekleyen onayı
sorgularak kullanıcıya gösterir). Kullanıcı yanıt vermezse 5 dk sonra red.

TAK-ÇIKAR: bu klasörü silmek EL'i sistemden söker; çekirdekte bu modüle
sabit bağımlılık yoktur. Onay altyapısı (cekirdek/onay.py) genel hizmettir,
EL'siz de zararsız durur.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Dict

from cekirdek.onay import TEKIL_KAPICI
from yetenekler.el import eylemler as EL


def _girdi_coz(metin: str) -> Dict[str, object]:
    """modul_girdisi'ni (JSON ya da düz komut) eylem+parametreye çevirir."""
    metin = (metin or "").strip()
    if not metin:
        return {}
    # 1) JSON dene (karar merkezinin varsayılan çıktısı)
    m = re.search(r"\{.*\}", metin, flags=re.S)
    if m:
        try:
            veri = json.loads(m.group(0))
            if isinstance(veri, dict):
                if veri.get("eylem"):
                    return veri
                if "hedef" in veri or "icerik" in veri:      # düz parametre paketi
                    veri.setdefault("eylem", "dosya_yaz")
                    return veri
        except Exception:
            pass
    # 2) düz komut sözdizimi:  yaz <yol> || içerik   /   oku <yol>  vb.
    govde = metin.replace("||", "\x00").replace("|", "\x00")
    sozcuk = govde.split("\x00")
    ilk = sozcuk[0].split(maxsplit=2)
    if not ilk:
        return {}
    bas = ilk[0].lower().lstrip("/")
    kalip = {
        "oku": ("dosya_oku", ["hedef"]),
        "listele": ("klasor_listele", ["hedef"]),
        "yaz": ("dosya_yaz", ["hedef", "icerik"]),
        "ekle": ("dosya_yaz", ["hedef", "icerik"]),
        "sil": ("dosya_sil", ["hedef"]),
        "tasi": ("dosya_tasi", ["kaynak", "hedef"]),
        "ac": ("program_ac", ["hedef"]),
        "kapat": ("program_kapat", ["hedef"]),
        "surecler": ("program_listele", ["sorgu"]),
        "duzelt": ("dosya_duzelt", ["hedef", "eski", "yeni"]),
    }.get(bas)
    if not kalip:
        return {"eylem": "", "hata": f"Bilinmeyen EL komutu '{bas}'. "
                "Geçerliler: oku, listele, yaz, ekle, sil, tasi, duzelt, ac, kapat, surecler"}
    eylem, alan_adlari = kalip
    argumanlar = ilk[1:] + [p.strip() for p in sozcuk[1:] if p.strip()]
    parametre = {"eylem": eylem}
    for i, ad in enumerate(alan_adlari):
        if i < len(argumanlar):
            parametre[ad] = argumanlar[i]
    if bas == "ekle":
        parametre["ekleyerek"] = True
    return parametre


def calistir(metin: str, **saglama) -> dict:
    """Yetenek sözleşmesinin giriş noktası.

    DÖNDÜRÜLEN SÖZLÜK:
      basarili, yanit, eylem, yol ... ve ONAY GEREKTİĞİNDE:
      onay_bekliyor=True, kimlik=<kart no>, hedef, eylem → gonderci bunu
      anlar ve sohbet mesajında 'El izin bekliyor' satırı döner.
    """
    girdi = _girdi_coz(metin)
    if girdi.get("hata"):
        return {"basarili": False, "yanit": girdi["hata"]}
    eylem = girdi.pop("eylem", "")
    if not eylem:
        return {"basarili": False,
                "yanit": "EL'e hangi eylem yapılacağı söylenmedi. Örnek: "
                         '{"eylem":"dosya_oku","hedef":"~/masaustu/not.txt"}'}

    # ---- serbest mi, onaya mı gidecek? ----
    hedef = girdi.get("hedef") or girdi.get("kaynak") or ""
    if eylem in EL._EYLEMLER and hedef:
        izin = TEKIL_KAPICI.denetle(eylem, hedef,
                                   girdi.pop("aciklama", ""), alan=EL._alan(hedef))
        if not izin["onayli"]:
            return {"basarili": False, "eylem": eylem,
                    "yanit": f"İzin verilmedi ({izin['kaynak']}). {izin['neden']}"}
        girdi["_onay_kaynagi"] = izin["kaynak"]
    elif eylem in EL._EYLEMLER:
        # hedefsiz ama izin isteyen eylem (program_kapat gibi) → hedef sorulur
        if eylem not in ("program_listele",):
            return {"basarili": False, "eylem": eylem,
                    "yanit": "EL: işlem yapılacak dosya/program belirtilmedi."}

    sonuc = EL.eylem_calistir(eylem, **girdi)
    sonuc["eylem"] = eylem
    return sonuc


sozlesme = {
    "kod": "el",
    "ad": "El (Dosya & Program)",
    "tur": "yetenek",
    "surum": "1.0",
    "aciklama": "Bilgisayarda dosya okur/yazar/düzenler/siler (çöp kutusuna), "
                "klasör açar, taşır; program başlatır ve süreç kapatır. "
                "Yazma/silme/değiştirme/kapatma kullanıcı onayına tabidir.",
    "gorev_anahtarlari": ["dosya", "klasör", "kaydet", "sil", "çöp", "taşı", "yedek",
                          "program aç", "uygulama aç", "kapat", "süreç", "process",
                          "belge", "txt", "pdf", "excel", "not defteri"],
    "cagri_ornekleri": [
        "'masaüstündeki not.txt içeriğini oku' → el({\"eylem\":\"dosya_oku\",\"hedef\":\"~/Desktop/not.txt\"})",
        "'bu raporu ~/belgeler/ozet.md dosyasına yaz' → el({\"eylem\":\"dosya_yaz\",\"hedef\":\"~/belgeler/ozet.md\",\"icerik\":\"...\"})",
        "'eski.txt içindeki X kelimesini Y yap' → el({\"eylem\":\"dosya_duzelt\",\"hedef\":\"eski.txt\",\"eski\":\"X\",\"yeni\":\"Y\"})",
        "'indirilenler/map.pdf'i çöpe at' → el({\"eylem\":\"dosya_sil\",\"hedef\":\"~/Downloads/map.pdf\"})",
        "'notepad aç' → el({\"eylem\":\"program_ac\",\"hedef\":\"notepad\"})",
        "'chrome'u kapat' → el({\"eylem\":\"program_kapat\",\"hedef\":\"chrome\"})",
    ],
    "calistir": calistir,
}
