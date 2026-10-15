# -*- coding: utf-8 -*-
"""HAFIZA KÖPRÜSÜ — yeteneklerin hafıza organına dokunmadan erişimi.

Yetenek klasörleri kendi başına taşınabilir kalsın diye hafızaya doğrudan
import yerine bu ince köprüden ulaşılır. Organ yoksa sessizce boş döner.
Ayrıca paneldeki hızlı arayüzler (tercih/öğren) buradan yazar.
"""
from __future__ import annotations

import os
import re

_TERCİH_DESEN = re.compile(
    r"(?:tercihim\s*:|tercih\s*:|benden hatırla\s*:|şunu öğren\s*:|"
    r"artık\s+.*\sisterim|bir daha\s+.*)[:\s]+(.{4,200})", re.I)


def _organ():
    try:
        from cekirdek.modul_iskeleti import TEKIL
        for m in TEKIL.tara():
            if m.get("kod") == "hafiza" and m.get("etkin"):
                return m
    except Exception:
        pass
    return None


def yerel_hafiza():
    organ = _organ()
    if not organ:
        return None
    try:
        from cekirdek.modul_iskeleti import TEKIL
        mod = TEKIL.sozluk.get("hafiza")
        if mod and hasattr(mod, "calistir"):
            # sozlesme nesnesindeki hafiza ornegine ulas
            ozel = getattr(mod, "_hafiza_ornegi", None)
            return ozel
    except Exception:
        pass
    return None


def tercihleri_getir() -> str:
    """bellek.md içeriğini döner (yetenek kanıt dosyasına eklenir)."""
    try:
        from cekirdek import yapilandirma
        yol = os.path.join(yapilandirma.HAFIZA_DIZIN, "bellek.md")
        if os.path.isfile(yol):
            with open(yol, encoding="utf-8") as f:
                return f.read().strip()[:1500]
    except Exception:
        pass
    return ""


def tercih_kaydet(cumle: str) -> bool:
    """Panel/hızlı arayüzden gelen tercihi kalıcı belleğe tek satır ekler."""
    cumle = (cumle or "").strip()
    if not cumle:
        return False
    try:
        from cekirdek import yapilandirma
        os.makedirs(yapilandirma.HAFIZA_DIZIN, exist_ok=True)
        yol = os.path.join(yapilandirma.HAFIZA_DIZIN, "bellek.md")
        var = ""
        if os.path.isfile(yol):
            with open(yol, encoding="utf-8") as f:
                var = f.read()
        if cumle.lower() in var.lower():
            return True     # zaten var, çift ekleme yok
        with open(yol, "a", encoding="utf-8") as f:
            f.write(f"- [Kullanıcı tercihi] {cumle}\n")
        return True
    except Exception:
        return False
