# -*- coding: utf-8 -*-
"""ÜRETİM PANELİ SUNUCUSU — Flask.

Tüm sistem bu arayüzden kontrol edilir:
  • Sohbet penceresi (sağ)  • Sol panel (oturumlar/modüller/durum)
  • Üst menüler (Ayarlar, Modüller, Sistem)  • Ayarlar alanı: Ollama tarama +
    rutin/ağır/sınıflandırma model seçimi.
"""
from __future__ import annotations

import os
import time
import traceback

from flask import Flask, jsonify, render_template, request

from cekirdek import yapilandirma
from cekirdek.gonderci import GorevGonderici
from cekirdek.modul_iskeleti import TEKIL, TUR_ORGAN, TUR_YETENEK

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(_KOK, "web"),
    static_folder=os.path.join(_KOK, "web", "statik"),
)

GOVDE: GorevGonderici | None = None


def govde() -> GorevGonderici:
    global GOVDE
    if GOVDE is None:
        GOVDE = GorevGonderici()
        GOVDE.baslat()
    return GOVDE


# ---------------- sayfalar ----------------
@app.route("/")
def ana_sayfa():
    return render_template("panel.html")


# ---------------- durum / ön kontroller ----------------
@app.route("/api/durum")
def api_durum():
    g = govde()
    ayar = yapilandirma.yukle()
    canli = g.ollama.canli_mi()
    surum = ""
    modeller = []
    hata = ""
    if canli:
        try:
            surum = g.ollama.surumu_al()
            modeller = g.ollama.modelleri_tara()
        except Exception as e:
            hata = str(e)[:200]
    else:
        hata = "Ollama çalışmıyor veya adres hatalı."
    return jsonify({
        "ollama_canli": canli, "ollama_surum": surum, "modeller": modeller,
        "hata": hata, "ayarlar": ayar,
        "secili_oturum": g.aktif_oturum,
        "zaman": time.strftime("%H:%M:%S"),
    })


# ---------------- ayarlar ----------------
@app.route("/api/ayarlar", methods=["GET", "POST"])
def api_ayarlar():
    if request.method == "GET":
        return jsonify(yapilandirma.yukle())
    veri = request.get_json(force=True)
    yeni = yapilandirma.guncelle(veri)
    govde().ayar = yeni
    return jsonify(yeni)


@app.route("/api/model_test", methods=["POST"])
def api_model_test():
    ad = request.get_json(force=True).get("model", "")
    sonuc = govde().ollama.sayisal_test(ad)
    return jsonify(sonuc)


# ---------------- modüller (organ/yetenek) ----------------
@app.route("/api/moduller")
def api_moduller():
    kayitlar = TEKIL.tara()
    calisan = sorted(getattr(TEKIL, "_organ_calisan", set()))
    return jsonify({"moduller": kayitlar, "calisan_organlar": calisan})


@app.route("/api/modul_etkinlik", methods=["POST"])
def api_modul_etkinlik():
    v = request.get_json(force=True)
    return jsonify(TEKIL.etkinlik_ayarla(v["kod"], v["tur"], bool(v["etkin"])))


@app.route("/api/modul_cagir", methods=["POST"])
def api_modul_cagir():
    v = request.get_json(force=True)
    return jsonify(TEKIL.modulu_calistir(v["kod"], v.get("girdi", "")))


# ---------------- sohbet ----------------
@app.route("/api/sohbet", methods=["POST"])
def api_sohbet():
    v = request.get_json(force=True)
    metin = (v.get("mesaj") or "").strip()
    oid = v.get("oturum") or None
    zorla_model = v.get("model", "")
    zorla_modul = v.get("modul", "")
    if not metin:
        return jsonify({"hata": "Boş mesaj."})
    g = govde()
    # doğrudan yetenek çağırma kısayolu: "/arama sorgu"
    parcalar = metin.strip().split(maxsplit=1)
    ilk = parcalar[0]
    if ilk.startswith("/") and len(ilk) > 1:
        kod = ilk[1:].lower()
        girdi = parcalar[1] if len(parcalar) > 1 else ""
        if kod not in TEKIL.sozluk:
            return jsonify({"yanit": "", "hata": f"Bilinmeyen modül komutu: {ilk}. "
                          "Sol paneldeki modül listesinden kodları görebilirsiniz."})
        sonuc = TEKIL.modulu_calistir(kod, girdi)
        metin_yanit = sonuc.get("yanit") or sonuc.get("hata", "")
        g.hafiza.kaydet(g.aktif_oturum, "user", metin)
        if metin_yanit:
            g.hafiza.kaydet(g.aktif_oturum, "assistant", metin_yanit,
                            {"komut": kod})
        return jsonify({"yanit": metin_yanit,
                        "karar": {"kaynak": "komut", "modul": kod},
                        "adimlar": [{"adim": f"doğrudan komut: /{kod}"}],
                        "model": "", "oturum": g.aktif_oturum})
    try:
        iz = g.isle(metin, oturum=oid, zorla_model=zorla_model,
                    zorla_modul=zorla_modul)
        return jsonify(iz)
    except Exception:
        return jsonify({"hata": "Sunucu hatası:\n" + traceback.format_exc()[-600:]})


@app.route("/api/gecmis/<oid>")
def api_gecmis(oid):
    return jsonify({"mesajlar": govde().hafiza.yerel.mesajlari_getir(oid)})


@app.route("/api/ozet/<oid>")
def api_ozet(oid):
    return jsonify({"oturum_ozeti": govde().hafiza.yerel.ozet_oku(oid),
                    "kalici_bellek": govde().hafiza.yerel.bellek_oku()})


@app.route("/api/oturum_yeni", methods=["POST"])
def api_oturum_yeni():
    ad = request.get_json(force=True).get("ad", "")
    oid = govde().yeni_oturum(ad)
    return jsonify({"oturum": oid, "ad": ad or oid})


@app.route("/api/hafiza_ara", methods=["POST"])
def api_hafiza_ara():
    v = request.get_json(force=True)
    return jsonify({"sonuclar": govde().hafiza.ara(v.get("sorgu", ""),
                                                    v.get("oturum", ""))})


@app.route("/api/sohbetler")
def api_sohbetler():
    liste = []
    for f in sorted(os.listdir(yapilandirma.SOHBET_DIZIN)):
        if f.endswith(".jsonl"):
            yol = os.path.join(yapilandirma.SOHBET_DIZIN, f)
            with open(yol, encoding="utf-8") as fh:
                satir = sum(1 for _ in fh)
            liste.append({"oturum": f[:-6], "mesaj_sayisi": satir,
                          "boyut_kb": round(os.path.getsize(yol) / 1024, 1)})
    return jsonify(liste)
