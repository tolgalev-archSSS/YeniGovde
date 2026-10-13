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
from cekirdek.onay import TEKIL_KAPICI, BEKLEME_SURESI_SN

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


# ---------------- modül TAK / SÖK (kaldırma merkezi) ----------------
MODUL_SOK_DIZIN = os.path.join(yapilandirma.VERI_DIZIN, "sokulen_moduller")


def _modul_klasoru(kod: str, tur: str):
    taban = yapilandirma.ORGAN_DIZIN if tur == TUR_ORGAN else \
        yapilandirma.YETENEK_DIZIN
    yol = os.path.join(taban, kod)
    return yol if os.path.isdir(yol) else ""


@app.route("/api/modul_sok", methods=["POST"])
def api_modul_sok():
    """Modülü çalıştırmadan çıkarır ve klasörünü geri alınabilir arşive taşır.

    Silme DEĞİL: veri/sokulen_moduller/<tur>/<kod> altına gider; 'geri kur'
    ile aynı yerden geri takılır. Kalıcı silmek isteyen arşiv klasörünü elle
    siler (ya da dosya yöneticisinden).
    """
    import shutil
    v = request.get_json(force=True)
    kod, tur = v.get("kod", ""), v.get("tur", "")
    if not kod or tur not in (TUR_ORGAN, TUR_YETENEK):
        return jsonify({"basarili": False, "neden": "kod/tur hatalı"})
    kaynak = _modul_klasoru(kod, tur)
    if not kaynak:
        return jsonify({"basarili": False, "neden": f"{kod} klasörü bulunamadı"})
    hedef_kok = os.path.join(MODUL_SOK_DIZIN, tur)
    hedef = os.path.join(hedef_kok, kod)
    os.makedirs(hedef_kok, exist_ok=True)
    if os.path.exists(hedef):
        hedef = hedef + "_" + time.strftime("%H%M%S")
    try:
        # önce etkinlikten çıkar → çalışan organ durdurulur, sözlükten düşer
        TEKIL.etkinlik_ayarla(kod, tur, False)
        shutil.move(kaynak, hedef)
        TEKIL.tara(yeniden=True)
        return jsonify({"basarili": True, "arsiv": hedef,
                        "not": "Klasör arşive taşındı; 'Geri Kur' ile geri takılır."})
    except Exception as e:
        return jsonify({"basarili": False, "neden": str(e)[:200]})


@app.route("/api/modul_geri_kur", methods=["POST"])
def api_modul_geri_kur():
    """Arşivdeki (sökülmüş) modülü eski yerine geri taşır."""
    import shutil
    v = request.get_json(force=True)
    kod, tur = v.get("kod", ""), v.get("tur", "")
    arsiv_kok = os.path.join(MODUL_SOK_DIZIN, tur)
    if not os.path.isdir(arsiv_kok):
        return jsonify({"basarili": False, "neden": "arşiv boş"})
    adaylar = [d for d in sorted(os.listdir(arsiv_kok), reverse=True)
               if d == kod or d.startswith(kod + "_")]
    if not adaylar:
        return jsonify({"basarili": False, "neden": f"arşivde {kod} yok"})
    kaynak = os.path.join(arsiv_kok, adaylar[0])
    taban = yapilandirma.ORGAN_DIZIN if tur == TUR_ORGAN else \
        yapilandirma.YETENEK_DIZIN
    hedef = os.path.join(taban, kod)
    if os.path.exists(hedef):
        return jsonify({"basarili": False, "neden": f"{hedef} zaten var"})
    try:
        shutil.move(kaynak, hedef)
        TEKIL.tara(yeniden=True)
        TEKIL.etkinlik_ayarla(kod, tur, True)
        return jsonify({"basarili": True, "yol": hedef})
    except Exception as e:
        return jsonify({"basarili": False, "neden": str(e)[:200]})


@app.route("/api/modul_sokulenler")
def api_modul_sokulenler():
    liste = []
    for tur in (TUR_ORGAN, TUR_YETENEK):
        kok = os.path.join(MODUL_SOK_DIZIN, tur)
        if os.path.isdir(kok):
            for ad in sorted(os.listdir(kok)):
                liste.append({"arsiv_adi": ad, "kod": ad.split("_")[0],
                              "tur": tur})
    return jsonify({"sokulenler": liste})


@app.route("/api/sonuclar_bekleyen")
def api_sonuclar_bekleyen():
    """Onay sonrası arka planda tamamlanan işlerin sohbet yanıtları."""
    oid = request.args.get("oturum", "genel")
    return jsonify({"sonuclar": GONDERCI.sonuclari_al(oid)})


@app.route("/api/modul_cagir", methods=["POST"])
def api_modul_cagir():
    v = request.get_json(force=True)
    return jsonify(TEKIL.modulu_calistir(v["kod"], v.get("girdi", "")))


# ---------------- onay / izin sistemi (kapıcı) ----------------
@app.route("/api/onaylar")
def api_onaylar():
    """Panel bu ucu ~2 sn'de bir yoklar; bekleyen kartları getirir."""
    return jsonify({"bekleyenler": TEKIL_KAPICI.bekleyenleri_getir(),
                    "sure_sn": BEKLEME_SURESI_SN})


@app.route("/api/onay_ver", methods=["POST"])
def api_onay_ver():
    v = request.get_json(force=True)
    return jsonify(TEKIL_KAPICI.yanit_ver(v.get("kimlik", ""),
                                          v.get("secenek", "")))


@app.route("/api/el_izinleri")
def api_el_izinleri():
    return jsonify({"kalici": TEKIL_KAPICI.defterdeki_izinler(),
                    "oturum": TEKIL_KAPICI.oturum_izinleri()})


@app.route("/api/el_izin_iptal", methods=["POST"])
def api_el_izin_iptal():
    v = request.get_json(force=True)
    return jsonify({"basarili": TEKIL_KAPICI.izin_iptal(v.get("anahtar", ""))})


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
