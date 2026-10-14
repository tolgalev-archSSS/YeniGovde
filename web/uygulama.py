# -*- coding: utf-8 -*-
"""ÜRETİM PANELİ SUNUCUSU — Flask.

Tüm sistem bu arayüzden kontrol edilir:
  • Sohbet penceresi (sağ)  • Sol panel (oturumlar/modüller/durum)
  • Üst menüler (Ayarlar, Modüller, Sistem)  • Ayarlar alanı: Ollama tarama +
    rutin/ağır/sınıflandırma model seçimi.
"""
from __future__ import annotations

import os
import re
import sys
import time
import traceback
from typing import List

from flask import Flask, jsonify, render_template, request

from cekirdek import yapilandirma
from cekirdek.gonderci import GorevGonderici
from cekirdek.modul_iskeleti import TEKIL, TUR_ORGAN, TUR_YETENEK, TUR_NODE
from cekirdek.onay import TEKIL_KAPICI, BEKLEME_SURESI_SN

# arastirmaci'nin güncel-veri birimini (hava/kur) üst panel için kullan:
# arastirmaci klasörü paket değil → dosya yolundan manuel yükle
import importlib.util as _ilu

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_gv_spec = _ilu.spec_from_file_location(
    "guncel_veri_birimi",
    os.path.join(_KOK, "yetenekler", "arastirmaci", "birimler",
                 "guncel_veri_birimi.py"))
_gv_mod = _ilu.module_from_spec(_gv_spec)
_gv_spec.loader.exec_module(_gv_mod)

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
        "yol_organ": yapilandirma.ORGAN_DIZIN.replace("\\", "/"),
        "yol_yetenek": yapilandirma.YETENEK_DIZIN.replace("\\", "/"),
        "yol_arsiv": yapilandirma.KABUL_DIZIN.replace("\\", "/"),
        "zaman": time.strftime("%H:%M:%S"),
    })


# ---------------- üst panel: hava + kur (yalnız açılışta çekilir) ----------
@app.route("/api/pencere_veri")
def api_pencere_veri():
    """İstanbul bugün+yarın hava ve USD/TRY kuru — guncel_veri_birimi'nden.
    Panel bunu SADECE ilk açılışta çağırır (sürekli tetikleme yok)."""
    sehir = request.args.get("sehir", "istanbul")
    try:
        hava = _gv_mod._hava(sehir)
    except Exception as e:
        hava = [{"baslik": f"Hava alınamadı ({sehir})", "ozet": str(e)[:120]}]
    try:
        doviz = _gv_mod._doviz("dolar")
    except Exception as e:
        doviz = [{"baslik": "Kur alınamadı", "ozet": str(e)[:120]}]
    return jsonify({"hava": hava, "kur": doviz})


# ---------------- üst panel: anlık döviz hesabı ---------------------------
@app.route("/api/dovus_hesapla", methods=["POST"])
def api_dovus_hesapla():
    """Panel'deki 'miktar → TL' kutusu: 5 USD yazınca anlık kurla çarpar.
    Kur değeri guncel_veri_birimi API'sinden birebir alınır (tahmin yok)."""
    v = request.get_json(force=True)
    try:
        miktar = float(v.get("miktar", 0))
    except (TypeError, ValueError):
        return jsonify({"basarili": False, "hata": "miktar sayı olmalı"})
    para = str(v.get("para", "USD")).upper()
    if para not in ("USD", "EUR", "GBP"):
        return jsonify({"basarili": False, "hata": "desteklenen: USD/EUR/GBP"})
    try:
        sonuc = _gv_mod._doviz(para.lower())[0]
        import re as _re
        m = _re.search(r"≈?\s*([\d.,]+)\s*TL", sonuc["ozet"])
        kur = float(m.group(1).replace(",", ".")) if m else None
        if kur is None:
            raise ValueError("kur ayrıştırılamadı: " + sonuc["ozet"][:80])
        return jsonify({"basarili": True, "kur": kur, "tl": miktar * kur,
                        "para": para, "miktar": miktar,
                        "zaman": sonuc.get("guncellik", ""),
                        "kaynak": sonuc.get("kaynak_birimi", "")})
    except Exception as e:
        return jsonify({"basarili": False, "hata": str(e)[:160]})


# ---------------- tercih defteri (hafıza köprüsü) -------------------------
@app.route("/api/tercih_kaydet", methods=["POST"])
def api_tercih_kaydet():
    """Panel'deki 'Tercih Kaydet' kutusu → kalıcı belleğe satır ekler.
    Aramacı her aramada bu defteri kanıt dosyasına ekler; AĞIR model
    önerileri kullanıcının ihtiyaçlarına göre şekillendirir."""
    from cekirdek.hafiza_kopru import tercih_kaydet
    v = request.get_json(force=True)
    cumle = (v.get("cumle") or "").strip()
    if not cumle:
        return jsonify({"basarili": False, "neden": "boş cümle"})
    return jsonify({"basarili": tercih_kaydet(cumle), "kaydedilen": cumle})


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
    taban = {TUR_ORGAN: yapilandirma.ORGAN_DIZIN,
             TUR_NODE: yapilandirma.NODE_DIZIN}.get(tur,
                                                    yapilandirma.YETENEK_DIZIN)
    yol = os.path.join(taban, kod)
    return yol if os.path.isdir(yol) else ""


def _arsiv_kodu(ad: str) -> str:
    """Kabul arşivindeki klasör adından modül kodunu çıkarır.

    Kurallar:
      • 'modul_123456'  → zaman damgası (6 hane) sökülen gerçek kod 'modul'
      • 'x_yetenek', 'x_node', 'x_organ' → tür soneki düşülür → 'x'
      • aksi halde ad olduğu gibi kalır ('benim_node' gibi kullanıcı adları!)
    """
    m = re.match(r"^(.*?)_\d{6}$", ad)
    if m:
        ad = m.group(1)
    for son in ("_yetenek", "_organ", "_node"):
        if ad.endswith(son) and len(ad) > len(son):
            return ad[: -len(son)]
    return ad


def _kabul_eslesmeleri(dosya_adi: str) -> List[str]:
    """nodeller/kabul içindeki zaman damgalı kopyalar: '<kod>_HHMMSS'.
    Tam ad eşleşmesi de kabul edilir (kullanıcı '_node' sonekli isim yazmışsa)."""
    kok = yapilandirma.KABUL_DIZIN
    if not os.path.isdir(kok):
        return []
    return [d for d in sorted(os.listdir(kok), reverse=True)
            if d == dosya_adi or d.startswith(dosya_adi + "_")]


@app.route("/api/modul_sok", methods=["POST"])
def api_modul_sok():
    """Modülü çalıştırmadan çıkarır ve klasörünü GERİ ALINABİLİR KABUL
    ARŞİVİNE taşır.

    Silme DEĞİL: kullanıcı söktüğünü tekrar aktif edebilsin diye klasör
    nodeller/kabul/<kod>_[zaman] altına gider — Ayarlar → Node Yönetimi'nde
    'Kabuldekiler' listesinde görünür ve tek tıkla geri kurulur. Organ/
    yetenek/node hepsi için aynı kural geçerlidir.
    """
    import shutil
    v = request.get_json(force=True)
    kod, tur = v.get("kod", ""), v.get("tur", "")
    if not kod or tur not in (TUR_ORGAN, TUR_YETENEK, TUR_NODE):
        return jsonify({"basarili": False, "neden": "kod/tur hatalı"})
    kaynak = _modul_klasoru(kod, tur)
    if not kaynak:
        return jsonify({"basarili": False, "neden": f"{kod} klasörü bulunamadı"})
    hedef_kok = yapilandirma.KABUL_DIZIN          # ← sokülen değil, KABUL
    os.makedirs(hedef_kok, exist_ok=True)
    hedef = os.path.join(hedef_kok, kod)
    if os.path.exists(hedef):
        hedef = hedef + "_" + time.strftime("%H%M%S")
    try:
        # önce etkinlikten çıkar → çalışan organ durdurulur, sözlükten düşer
        TEKIL.etkinlik_ayarla(kod, tur, False)
        shutil.move(kaynak, hedef)
        TEKIL.tara(yeniden=True)
        return jsonify({"basarili": True, "arsiv": hedef,
                        "not": ("Klasör nodeller/kabul/ arşivine taşındı; "
                                "Ayarlar → Node Yönetimi'nden geri kurabilirsin.")})
    except Exception as e:
        return jsonify({"basarili": False, "neden": str(e)[:200]})


@app.route("/api/modul_geri_kur", methods=["POST"])
def api_modul_geri_kur():
    """Kabul arşivindeki (sökülmüş ya da dışarıdan yazılmış) modülü eski
    yerine geri taşır. '<kod>' veya '<kod>_HHMMSS' adıyla arayebilir."""
    import shutil
    v = request.get_json(force=True)
    kod, tur = v.get("kod", ""), v.get("tur", "")
    arsiv_kok = yapilandirma.KABUL_DIZIN
    if not os.path.isdir(arsiv_kok):
        return jsonify({"basarili": False, "neden": "kabul klasörü yok"})
    adaylar = _kabul_eslesmeleri(kod)
    if not adaylar:
        return jsonify({"basarili": False, "neden": f"nodeller/kabul içinde {kod} yok"})
    kaynak = os.path.join(arsiv_kok, adaylar[0])
    taban = {TUR_ORGAN: yapilandirma.ORGAN_DIZIN,
             TUR_NODE: yapilandirma.NODE_DIZIN}.get(tur,
                                                    yapilandirma.YETENEK_DIZIN)
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
    """Kabul arşivini listeler — yeni yer: nodeller/kabul/ (sokülen DEĞİL)."""
    liste = []
    kok = yapilandirma.KABUL_DIZIN
    if os.path.isdir(kok):
        for ad in sorted(os.listdir(kok)):
            yol = os.path.join(kok, ad)
            if not os.path.isdir(yol) or ad.startswith("."):
                continue
            # türü içeriden tahmin et: modul_bilgisi.py / modul.py içindeki 'tur'
            tur = "yetenek"
            for dosya in ("modul_bilgisi.py", "modul.py"):
                p = os.path.join(yol, dosya)
                if os.path.exists(p):
                    try:
                        with open(p, encoding="utf-8") as fh:
                            icerik = fh.read()
                        m = re.search(r'"tur"\s*:\s*"(\w+)"', icerik)
                        if m:
                            tur = m.group(1)
                            break
                    except Exception:
                        pass
            liste.append({"arsiv_adi": ad, "kod": _arsiv_kodu(ad),
                          "tur": tur})
    return jsonify({"sokulenler": liste})


# ---------------- NODE YÖNETİMİ (Ayarlar menüsü) ---------------------------
@app.route("/api/node_listesi")
def api_node_listesi():
    """Üç bölüm birden döner: yüklü node'lar, kabuldekiler, arşivden
    (eski sokülen/) gelenler — panelde tek ekranda görünsün diye."""
    yukluler = []
    kok = yapilandirma.NODE_DIZIN
    if os.path.isdir(kok):
        for ad in sorted(os.listdir(kok)):
            if ad in ("kabul", "sokulen", "indirilen") or ad.startswith("."):
                continue
            yol = os.path.join(kok, ad)
            if not os.path.isdir(yol):
                continue
            bilgi_yol = os.path.join(yol, "modul_bilgisi.py")
            ana_yol = os.path.join(yol, "modul.py")
            aciklama, surum = "", "?"
            for p in (ana_yol, bilgi_yol):
                if os.path.exists(p):
                    try:
                        with open(p, encoding="utf-8") as fh:
                            metin = fh.read()
                        m = re.search(r'"aciklama"\s*:\s*\(?["\']([^"\']+)', metin)
                        if m and not aciklama:
                            aciklama = m.group(1)[:160]
                        m2 = re.search(r'"surum"\s*:\s*["\']([^"\']+)', metin)
                        if m2:
                            surum = m2.group(1)
                    except Exception:
                        pass
            kayit = next((k for k in TEKIL.tara()
                          if k["kod"] == ad and k["tur"] == TUR_NODE), None)
            yukluler.append({"kod": ad, "ad": (kayit or {}).get("ad", ad),
                             "aciklama": (kayit or {}).get("aciklama") or aciklama,
                             "surum": surum,
                             "etkin": (kayit or {}).get("etkin", True),
                             "hata": (kayit or {}).get("hata", "")})
    kabul = []
    kk = yapilandirma.KABUL_DIZIN
    if os.path.isdir(kk):
        for ad in sorted(os.listdir(kk)):
            yol = os.path.join(kk, ad)
            if not os.path.isdir(yol) or ad.startswith("."):
                continue
            hazir = os.path.exists(os.path.join(yol, "modul.py")) or \
                os.path.exists(os.path.join(yol, "modul_bilgisi.py"))
            kabul.append({"arsiv_adi": ad, "kod": _arsiv_kodu(ad),
                          "hazir": hazir, "yol": yol})
    eski_arsiv = []
    ek = MODUL_SOK_DIZIN   # veri/sokulen_moduller — eski yerleşim, yedek
    if os.path.isdir(ek):
        for tur_alt in (TUR_ORGAN, TUR_YETENEK, TUR_NODE):
            alt = os.path.join(ek, tur_alt)
            if os.path.isdir(alt):
                for ad in sorted(os.listdir(alt)):
                    if os.path.isdir(os.path.join(alt, ad)):
                        eski_arsiv.append({"arsiv_adi": ad,
                                           "kod": _arsiv_kodu(ad),
                                           "tur": tur_alt, "yer": alt})
    return jsonify({"yuklu": yukluler, "kabul": kabul,
                    "eski_arsiv": eski_arsiv})


@app.route("/api/node_onayla", methods=["POST"])
def api_node_onayla():
    """nodeller/kabul/<ad> klasörünü doğrula → nodeller/'e taşı (yüklü node)."""
    v = request.get_json(force=True)
    ad = str(v.get("dosya") or "").strip("/")
    if not ad:
        return jsonify({"basarili": False, "neden": "dosya adı boş"})
    kaynak = os.path.join(yapilandirma.KABUL_DIZIN, ad)
    if not os.path.isdir(kaynak):
        return jsonify({"basarili": False, "neden": f"kabul/{ad} yok"})
    izin = TEKIL_KAPICI.denetle("node_kabul", ad,
                                f"Dışarıdan/arşivden '{ad}' node'u onaylanıp "
                                "yüklü node'lara taşınacak (kod çalıştırma "
                                "yetkisi verir).", alan="node")
    if not izin.get("onayli"):
        return jsonify({"basarili": False,
                        "neden": "Onay verilmedi: " +
                                 (izin.get("neden") or izin.get("kaynak", ""))})
    # paket denetimi: modul.py + sozlesme + calistir
    spec = None
    try:
        import importlib.util as _iu
        p = os.path.join(kaynak, "modul.py")
        if not os.path.exists(p):
            return jsonify({"basarili": False,
                            "neden": "modul.py yok — sözleşme paketi reddedildi"})
        spec = _iu.spec_from_file_location("_node_test_", p)
        mod = _iu.module_from_spec(spec)
        sys.path.insert(0, kaynak)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "sozlesme") or not callable(getattr(mod, "calistir", None)):
            return jsonify({"basarili": False,
                            "neden": "'sozlesme' ve/veya 'calistir()' yok"})
    except Exception as e:
        return jsonify({"basarili": False,
                        "neden": f"paket bozuk: {type(e).__name__}: {str(e)[:140]}"})
    hedef_kod = _arsiv_kodu(ad)
    hedef = os.path.join(yapilandirma.NODE_DIZIN, hedef_kod)
    if os.path.exists(hedef):
        hedef = hedef + "_" + time.strftime("%H%M%S")
    try:
        import shutil
        shutil.move(kaynak, hedef)
        TEKIL.tara(yeniden=True)
        return jsonify({"basarili": True, "yol": hedef, "kod": hedef_kod,
                        "yanit": f"✅ '{os.path.basename(hedef)}' yüklendi."})
    except Exception as e:
        return jsonify({"basarili": False, "neden": str(e)[:200]})


@app.route("/api/eski_arsivi_kabule_tasi", methods=["POST"])
def api_eski_arsivi_kabule_tasi():
    """Eski 'veri/sokulen_moduller' altındaki klasörleri nodeller/kabul'e
    taşır (geçiş yardımı — kullanıcı istediğinde)."""
    import shutil
    v = request.get_json(force=True)
    tasinar = []
    ek = MODUL_SOK_DIZIN
    if not os.path.isdir(ek):
        return jsonify({"basarili": True, "tasinan": [], "not": "eski arşiv yok"})
    for tur_alt in (TUR_ORGAN, TUR_YETENEK, TUR_NODE):
        alt = os.path.join(ek, tur_alt)
        if not os.path.isdir(alt):
            continue
        for ad in sorted(os.listdir(alt)):
            src = os.path.join(alt, ad)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(yapilandirma.KABUL_DIZIN, ad)
            if os.path.exists(dst):
                dst = dst + "_" + time.strftime("%H%M%S")
            try:
                shutil.move(src, dst)
                tasinar.append({"eski": src, "yeni": dst})
            except Exception as e:
                return jsonify({"basarili": False, "neden": str(e)[:200]})
    return jsonify({"basarili": True, "tasinan": tasinar})


@app.route("/api/sonuclar_bekleyen")
def api_sonuclar_bekleyen():
    """Onay sonrası arka planda tamamlanan işlerin sohbet yanıtları."""
    oid = request.args.get("oturum", "genel")
    return jsonify({"sonuclar": govde().sonuclari_al(oid)})


@app.route("/api/gecmis_yaz", methods=["POST"])
def api_gecmis_yaz():
    """Panel, arka plandan gelen sonuçları kullanıcıya gösterdikten sonra
    sohbete (ve hafızaya) kalıcı olarak yazar — böylece yenilemede kaybolmaz."""
    v = request.get_json(force=True)
    g = govde()
    oid = v.get("oturum") or g.aktif_oturum
    icerik = (v.get("icerik") or "").strip()
    rol = v.get("rol", "assistant")
    if not icerik:
        return jsonify({"basarili": False, "neden": "boş içerik"})
    g.hafiza.kaydet(oid, rol, icerik, {"kaynak": "arkaplan-sonuc",
                                       "model": v.get("model", "")})
    return jsonify({"basarili": True})


@app.route("/api/modul_cagir", methods=["POST"])
def api_modul_cagir():
    """Hızlı çağırma. Onay üretebilecek yetenekler (arastirmaci/el) arka
    planda işlenir; sonuç /api/sonuclar_bekleyen ile panele düşer."""
    v = request.get_json(force=True)
    kod, girdi = v["kod"], v.get("girdi", "")
    govde().aktif_oturum = v.get("oturum") or govde().aktif_oturum
    if kod in ("arastirmaci", "el"):
        import threading
        karar = {"kaynak": "hizli-cagri", "modul": kod, "agirlik": 0.7,
                 "model_secimi": "", "modul_girdisi": girdi}
        threading.Thread(target=govde()._arka_plan_isle,
                         args=(girdi, govde().aktif_oturum, karar, ""),
                         daemon=True).start()
        return jsonify({"arkaplan": True, "yanit":
                        f"'{kod}' arka planda çalışıyor; onay kartı çıkabilir, "
                        "sonuç sohbete düşecek."})
    return jsonify(TEKIL.modulu_calistir(kod, girdi))


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
