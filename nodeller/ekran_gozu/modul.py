# -*- coding: utf-8 -*-
"""EKRAN GÖZÜ — sistemin gözü: ekrana ucuz, yerel, tek-kare göz atma.

Neden "ucuz yöntem"? (tasarım kararı)
  • Ekran görüntüsü + OCR + pencere listesi = üç sinyal, sıfır bulut, sıfır GPU.
  • Pillow ImageGrab tek satırda tam ekranı yakalar (Win/macOS/Linux-X11).
  • Metin okuma varsa tesseract/pytesseract, yoksa yalnızca pencere başlıkları
    ve renk/bölge analizi döner — node yine de çökermez (kademeli yetenek).
  • Sürekli video YOK: kullanıcı/panel "bak" dedikçe tek kare; istenirse
    düşük frekanslı nöbetçi (her N sn'de bir değişim-piksel kontrolü).

OKU-ANLA-ZİHİN SİLKİ (eylem_oku_anla / zihin_analiz):
  • Ekrandaki İngilizce/Çince metin ya da hata mesajı → OCR → dil tespiti →
    Türkçe çeviri + "bu ne istiyor, neden oldu, ne yapmalısın" açıklaması.
  • Model kademeli seçilir: ayarlarda goruntu_modeli yazılıysa O (çok-modal,
    görseli de görür); değilse adında vision/llava/minicpm-v geçen yüklü model
    aranır; hiç yoksa rutin LLM yalnız OCR metniyle çalışır — zincir kopmaz.
  • Görsel işleme ÖNCE hafıza aranır: bellekteki geçmiş ekran olayları/
    tercihler analize bağlam olarak eklenir ("dün de aynı hatayı görmüştün").
  • Analiz sonucu belleğe iade edilir (konu etiketi + kısa not) — zamanla
    "kullanıcı X uygulamasında Y hatasıyla karşılaşıyor" profili oluşur.
  • Maliyet: hepsi yerel (tesseract CPU + Ollama). Bulut API anahtarı yok.

GÜVENLİK (ONAY_AKISI_TASARIM.md):
  • Tam ekran yakalama → serbest ama İLK KULLANIMDA onay kartı çıkarır
    ("göz_izin" | alan "dis-dunya" değil, "goz"): kullanıcı bir kez
    "oturum boyunca" derse bir daha sormaz.
  • Pencere/bölge ODAKLI tarama ve dosyaya kayıt → her seferinde onay.
  • Yakalanan kareler yalnızca bellekte özetlenir; disk'e varsayılan yazılmaz.

Eylemler:
  izleme_durumu → hangi araçlar var (ImageGrab/OCR/psutil), izin durumu
  ekran_tara    → tam ekran: pencereler + OCR metni + renk özeti
  oku_anla      → ekranı OKU + dil tespiti + Türkçe ÇEVİR/AÇIKLA (hata mesajı,
                  İngilizce/Çince metin, diyalog kutusu) — soru da verilebilir
  zihin_analiz  → kullanıcının paylaştığı görsel yolu/dosya adı üzerinden
                  hafıza eşleştirmeli derin analiz (bağlam + bellek notu)
  gorsel_oku    → verilen PNG/JPG dosyasını aynı zincirden geçir
  pencere_tara  → belirli pencere başlığını bul, kesip onu analiz et (ONAY)
  bolum_tara    → x,y,w,h bölgesini kesip analiz et (ONAY)
  gozetle       → arka plan nöbetçisi: N sn'de bir DEĞİŞİM olursa rapor biriktir
  durdur        → nöbetçiyi kapat
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
from typing import Dict, List

# ---------- kademeli yetenek yoklaması (node asla çökmez) ----------
try:
    from PIL import ImageGrab  # pip install pillow
    _VAR_IMAGEGRAB = True
except Exception:
    ImageGrab = None
    _VAR_IMAGEGRAB = False

try:
    import pytesseract  # kuruluysa OCR açık
    _VAR_OCR = True
except Exception:
    pytesseract = None
    _VAR_OCR = False

try:
    import psutil
    _VAR_PSUTIL = True
except Exception:
    psutil = None
    _VAR_PSUTIL = False


def _pencere_basliklari() -> List[str]:
    """En az maliyetli 'ekranda ne var' sinyali: süreç/pencere adları.

    Gerçek pencere başlığı OS'ye göre farklı API ister (win32gui/X11);
    node bunları deniyor, yoksa süreç adlarına düşüyor — hepsi sessiz.
    """
    basliklar: List[str] = []
    # 1) Windows: ctypes + user32 EnumWindows (bağımlılıksız!)
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        liste: List[str] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _say(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    if buf.value.strip():
                        liste.append(buf.value.strip())
            return True
        user32.EnumWindows(_say, 0)
        basliklar = liste
    except Exception:
        pass
    # 2) Linux/X11: wmctrl ya da xdotool (varsa)
    if not basliklar and _VAR_PSUTIL is not None:
        import subprocess
        for komut in (["wmctrl", "-l"], ["xdotool", "search", "--name", ".*"]):
            try:
                r = subprocess.run(komut, capture_output=True, text=True, timeout=4)
                if r.returncode == 0 and r.stdout.strip():
                    if komut[0] == "wmctrl":
                        basliklar = [ln.split(None, 3)[-1].strip()
                                     for ln in r.stdout.splitlines()[1:] if ln.strip()]
                    else:
                        basliklar = [x for x in r.stdout.split("\n") if x][:50]
                    break
            except Exception:
                continue
    # 3) En kötü ihtimal: GUI süreç adları (psutil ile)
    if not basliklar and _VAR_PSUTIL:
        gorunur = {"chrome", "firefox", "edge", "notepad", "code", "explorer",
                   "thunderbird", "vlc", "spotify", "teams", "slack", "discord",
                   "term", "gnome-terminal", "konsole", "powershell", "wt"}
        seen = set()
        for p in psutil.process_iter(["name"]):
            try:
                ad = (p.info["name"] or "").lower().replace(".exe", "")
                if ad in gorunur and ad not in seen:
                    seen.add(ad)
                    basliklar.append(ad)
            except Exception:
                continue
    return basliklar[:60]


def _ocr_metni(gorsel) -> str:
    """Kuruluysa metin oku; değilse boş (node yine çalışır).

    Kademeli dil stratejisi (maliyet sırasıyla):
      1) eng+tur — en yaygın iki dil tek geçişte
      2) sonuçta CJK/bozulma izi varsa chi_sim+eng ile ikinci geçiş
         (tesseract latin verisiyle Çince'yi karıştırıp 'garbage' üretebilir)
    Ek dil paketi yoksa tesseract hata verir → sessizce ilk sonuca düşerüz.
    """
    if not (_VAR_OCR and gorsel is not None):
        return ""
    metin = ""
    try:
        metin = pytesseract.image_to_string(gorsel, lang="eng+tur")
    except Exception:
        try:
            metin = pytesseract.image_to_string(gorsel)
        except Exception:
            return ""
    # OCR İngilizce/Çince metni Türkçe sanıp bozabilir → chi_sim ile ikinci geçiş
    if _chi_izlendi(metin):
        try:
            v2 = pytesseract.image_to_string(gorsel, lang="chi_sim+eng")
            if len(v2.strip()) >= len(metin.strip()) * 0.6:
                metin = v2
        except Exception:
            pass
    return re.sub(r"\n{3,}", "\n\n", metin).strip()


def _chi_izlendi(metin: str) -> bool:
    """OCR çıktısında Çince/Japonca/Korece karakter ya da tam-width noktalama
    bölgesi izi var mı? (ikinci geçiş tetiği)"""
    return bool(re.search(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef\uac00-\ud7af]",
                          metin or ""))


def _renk_ozeti(gorsel) -> str:
    """Baskın renkler + parlaklık: 'ekran açık mı/koyu tema mı' ipucu."""
    if gorsel is None:
        return ""
    try:
        k = gorsel.convert("RGB").resize((64, 36))
        piksel = list(k.getdata())
        ort = tuple(round(sum(p[i] for p in piksel) / len(piksel)) for i in range(3))
        parlaklik = round(sum(ort) / 3)
        # k-means'sız basit küme: en sık 3 renk kutusu
        kutular: Dict[tuple, int] = {}
        for p in piksel:
            anahtar = tuple(c // 40 * 40 for c in p)
            kutular[anahtar] = kutular.get(anahtar, 0) + 1
        ilk3 = sorted(kutular.items(), key=lambda x: -x[1])[:3]
        kar = ", ".join(f"#{r:02x}{g:02x}{b:02x} %{round(s / len(piksel) * 100)}"
                        for (r, g, b), s in ilk3)
        durum = "koyu tema/açık değil" if parlaklik < 70 else \
                ("parlak içerik" if parlaklik > 170 else "orta ton")
        return f"Ortalama RGB {ort} ({durum}); baskın renkler: {kar}"
    except Exception:
        return ""


def _kare_yakala(bolum=None):
    """Tam ya da kesilmiş kare döndürür; desteklenmeyen platformda None."""
    if not _VAR_IMAGEGRAB:
        return None
    try:
        if bolum:
            x, y, w, h = [int(v) for v in bolum]
            return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        return ImageGrab.grab(all_screens=True)
    except TypeError:               # eski Pillow: all_screens yok
        try:
            return (ImageGrab.grab(bbox=tuple(int(v) for v in bolum))
                    if bolum else ImageGrab.grab())
        except Exception:
            return None
    except Exception:
        return None


def _analiz(gorsel, sinir=1500) -> dict:
    metin = _ocr_metni(gorsel)
    return {"metin": metin[:sinir],
            "metin_uzunluk": len(metin),
            "boyut": list(gorsel.size) if gorsel else [],
            "renk": _renk_ozeti(gorsel)}


def _izin_al(eylem: str, hedef: str, aciklama: str) -> dict:
    """Kapıcıyı çağırır; kapıcı yoksa (test modu) serbest sayar."""
    try:
        from cekirdek.onay import TEKIL_KAPICI
        return TEKIL_KAPICI.denetle(eylem, hedef, aciklama, alan="goz")
    except Exception:
        return {"onayli": True, "kaynak": "kapici_yok", "neden": ""}


# ==================== NÖBETÇİ (gözetle) ====================
_nobet = {"aktif": False, "dur": threading.Event(), "rapor": [], "sure_sn": 30}


def _degisti_mi(eski, yeni) -> bool:
    """İki küçük kareyi 64x36'a indirip fark piksellerine bak — çok ucuz."""
    if eski is None or yeni is None:
        return True
    try:
        a = eski.convert("RGB").resize((64, 36)).getdata()
        b = yeni.convert("RGB").resize((64, 36)).getdata()
        fark = sum(1 for x, y in zip(a, b)
                   if abs(x[0] - y[0]) + abs(x[1] - y[1]) + abs(x[2] - y[2]) > 90)
        return fark >= 8          # ~%0.4 ekran değiştiyse "bir şey oldu"
    except Exception:
        return True


def _nobet_dongusu():
    onceki = None
    while not _nobet["dur"].wait(_nobet["sure_sn"]):
        kare = _kare_yakala()
        if kare is None:
            _nobet["rapor"].append({"zaman": time.strftime("%H:%M:%S"),
                                    "olay": "ekran yakalanamıyor (platform desteği)"})
            break
        if onceki is None or _degisti_mi(onceki, kare):
            oz = _analiz(kare, sinir=300)
            _nobet["rapor"].append({
                "zaman": time.strftime("%H:%M:%S"),
                "olay": "ekranda değişim",
                "pencereler": _pencere_basliklari()[:8],
                "metin": oz["metin"][:200]})
        onceki = kare
        _nobet["rapor"] = _nobet["rapor"][-20:]     # bellek sınırlı
    _nobet["aktif"] = False


# ==================== EYLEMLER ====================
def eylem_izleme_durumu(**s) -> dict:
    return {"basarili": True,
            "yanit": (f"Göz donanımı: ImageGrab={'var' if _VAR_IMAGEGRAB else 'YOK'}, "
                      f"OCR={'var' if _VAR_OCR else 'yok (yalnız pencere+renk)'},"
                      f" psutil={'var' if _VAR_PSUTIL else 'yok'}; "
                      f"nöbetçi={'ÇALIŞIYOR' if _nobet['aktif'] else 'kapalı'}"),
            "arac": {"imagegrab": _VAR_IMAGEGRAB, "ocr": _VAR_OCR,
                     "psutil": _VAR_PSUTIL},
            "nobetci_acik": _nobet["aktif"]}


def eylem_ekran_tara(**s) -> dict:
    izin = _izin_al("goz_ekran", "tam ekran",
                    "Ekran Gözü tam ekrana bakacak (kare diske yazılmaz).")
    if not izin.get("onayli"):
        return {"basarili": False, "yanit": "İzin verilmedi: " +
                (izin.get("neden") or izin.get("kaynak", ""))}
    kare = _kare_yakala()
    pencereler = _pencere_basliklari()
    if kare is None:
        return {"basarili": True,
                "yanit": ("[kısmi] Ekran karesi alınamadı (headless oturum ya da "
                          "Pillow kurulu değil) — OCR/renk yerine pencere listesi "
                          "dönülüyor: " + (", ".join(pencereler[:15]) or "(yok)")),
                "pencereler": pencereler, "kism": True}
    oz = _analiz(kare)
    satirlar = [f"Ekranda görünen: {', '.join(pencereler[:12]) or '(başlık alınamadı)'}",
                f"Kare boyutu: {oz['boyut']} · {oz['renk']}"]
    if oz["metin"]:
        satirlar.append("Okunan metin (OCR):\n" + oz["metin"])
    else:
        satirlar.append("(OCR kapalı ya da okunur metin yok — tesseract kurulsaydı "
                        "metin de gelirdi)")
    return {"basarili": True, "yanit": "\n".join(satirlar),
            "pencereler": pencereler, "ozet": oz, "onay": izin["kaynak"]}


def eylem_pencere_tara(baslik: str = "", **s) -> dict:
    if not baslik:
        return {"basarili": False, "yanit": "Hangi pencere? 'baslik' ver."}
    izin = _izin_al("goz_pencere", baslik,
                    f"'{baslik}' penceresi odaklı taranacak (onay gerekli).")
    if not izin.get("onayli"):
        return {"basarili": False, "yanit": "İzin verilmedi: " +
                (izin.get("neden") or izin.get("kaynak", ""))}
    tum = _pencere_basliklari()
    eslesen = [t for t in tum if baslik.lower() in t.lower()]
    kare = _kare_yakala()
    if kare is None:
        return {"basarili": bool(eslesen),
                "yanit": f"Kare alınamadı; pencere eşleşmesi: {eslesen or 'yok'}"}
    # ucuz yöntem: tam kareyi OCR'la, ilgili satırı süz (kesmek için konum gerekir)
    oz = _analiz(kare)
    ilgili = [ln for ln in oz["metin"].splitlines()
              if any(k in ln.lower() for k in baslik.lower().split())] if oz["metin"] else []
    return {"basarili": True,
            "yanit": (f"Pencere '{baslik}' → eşleşen: {eslesen[:3]}. "
                      + ("İlgili satırlar:\n" + "\n".join(ilgi[:10]) if ilgili
                         else "Odaklı metin bulunamadı (tam ekran OCR denendi).")),
            "eslesen": eslesen[:5]}


def eylem_bolum_tara(x: int = 0, y: int = 0, w: int = 400, h: int = 200, **s) -> dict:
    izin = _izin_al("goz_bolum", f"{x},{y},{w},{h}",
                    "Ekranın belirtilen bölgesi taranacak.")
    if not izin.get("onayli"):
        return {"basarili": False, "yanit": "İzin verilmedi: " +
                (izin.get("neden") or izin.get("kaynak", ""))}
    kare = _kare_yakala(bolum=(x, y, w, h))
    if kare is None:
        return {"basarili": False, "yanit": "Bölge karesi alınamadı (platform/Pillow)."}
    oz = _analiz(kare, sinir=800)
    return {"basarili": True,
            "yanit": f"Bölge {x},{y} {w}x{h}: " + (oz["metin"] or "(metin yok) ") +
                     "· " + oz["renk"], "ozet": oz}


def eylem_gozetle(sure_sn: int = 30, **s) -> dict:
    if _nobet["aktif"]:
        return {"basarili": True, "yanit": "Nöbetçi zaten çalışıyor.",
                "son_raporlar": _nobet["rapor"][-5:]}
    _nobet["sure_sn"] = max(10, int(sure_sn))
    _nobet["dur"] = threading.Event()
    _nobet["aktif"] = True
    threading.Thread(target=_nobet_dongusu, daemon=True).start()
    return {"basarili": True,
            "yanit": f"Nöbetçi başladı: her {_nobet['sure_sn']} sn'de ucuz "
                     "değişim kontrolü (küçük kare + piksel farkı). Değişimde "
                     "pencere/metin raporu birikir.",
            "durdurma": '"eylem":"durdur"'}


def eylem_durdur(**s) -> dict:
    if _nobet["aktif"]:
        _nobet["dur"].set()
    return {"basarili": True, "yanit": "Nöbetçi durduruldu.",
            "toplam_rapor": len(_nobet["rapor"]),
            "raporlar": _nobet["rapor"][-10:]}


# ==================== EKRAN OKUMA: gör → anla → açıkla ====================
_lingua_algic = None          # tek seferlik kurulur (~1 sn), sonra ~1 ms/cagri
_LINGUA_DENENDI = False


def _lingua_getir():
    """Hafif ve DOĞRU yerel dil algılayıcı 'lingua' (pip lingua-language-detector).

    Kurulu değilse None döner → aşağıdaki kuralcı betik-yöntemi devreye girer.
    Sistem 10 dille sınırlı tutulur: bellek ~50 MB, CPU'da milisaniye.
    """
    global _lingua_algic, _LINGUA_DENENDI
    if _LINGUA_DENENDI:
        return _lingua_algic
    _LINGUA_DENENDI = True
    try:
        from lingua import LanguageDetectorBuilder
        _lingua_algic = (LanguageDetectorBuilder
                         .from_languages(
                             *[getattr(__import__("lingua").Language, ad) for ad in
                               ("ENGLISH", "TURKISH", "CHINESE", "JAPANESE",
                                "KOREAN", "RUSSIAN", "GERMAN", "FRENCH",
                                "ARABIC", "PERSIAN")])
                         .build())
    except Exception:
        _lingua_algic = None
    return _lingua_algic


_ISO_ESLEK = {"english": "en", "turkish": "tr", "chinese": "zh",
              "japanese": "ja", "korean": "ko", "russian": "ru",
              "german": "de", "french": "fr", "arabic": "ar",
              "persian": "fa"}


def _dil_tespet(metin: str) -> str:
    """Dil tespiti: önce lingua (istatistiksel, kısa hata mesajlarında bile
    doğru), o yoksa kaba ama sıfır-bağımlılık betik sayacı: tr/zh/ja/ko/en."""
    if not metin:
        return "bos"
    a = _lingua_getir()
    if a is not None:
        try:
            r = a.detect_language_of(metin[:2000])
            if r is not None:
                return _ISO_ESLEK.get(r.name.lower(), r.name.lower()[:2])
        except Exception:
            pass
    sayaç = {"zh": 0, "ja_kana": 0, "ko": 0, "latin": 0}
    for c in metin:
        o = ord(c)
        if 0x3040 <= o <= 0x30FF:
            sayaç["ja_kana"] += 1
        elif 0xAC00 <= o <= 0xD7AF:
            sayaç["ko"] += 1
        elif 0x2E80 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF:
            sayaç["zh"] += 1
        elif ("a" <= c.lower() <= "z") or c in "çğıöşüÇĞİÖŞÜ":
            sayaç["latin"] += 1
    if sayaç["ja_kana"]:
        return "ja"
    if sayaç["ko"] > max(2, sayaç["latin"]):
        return "ko"
    tr_iz = re.search(r"\b(bir|ve|ile|değil|hata|için|şu|bu)\b", metin.lower())
    if sayaç["zh"] > max(4, sayaç["latin"] * 0.5):
        return "zh"
    if sayaç["latin"] == 0:
        return "bilinmeyen"
    return "tr-karisik" if tr_iz else "en"


_HATA_IZLERI = [r"\berror\b", r"\bexception\b", r"0x[0-9a-fA-F]{6,}",
                r"\bfailed\b", r"\bcannot\b", r"\bdenied\b", r"\bcrash",
                r"\btraceback\b", r"\bat .+\.(py|js|java|cs|go) line \d+",
                r"错误|失敗|エラー", r"\bpanic\b", r"\bfatal\b"]


def _hata_mi(metin: str) -> bool:
    t = metin or ""
    return sum(1 for p in _HATA_IZLERI if re.search(p, t, flags=re.I)) >= 1


def _gorsel_b64(gorsel) -> str:
    """PIL görselini Ollama'nın beklediği base64 string'e çevirir.

    Uzun kenar 1024 px'e küçültülür: OCR/analiz için yeterli, token/VRAM
    maliyetini düşürür (ucuzluk ilkesi). JPEG kalite 82 — metin okunur kalır.
    """
    if gorsel is None:
        return ""
    try:
        from PIL import Image as _Im
        g = gorsel.convert("RGB")
        w, h = g.size
        if max(w, h) > 1024:
            oran = 1024 / max(w, h)
            g = g.resize((int(w * oran), int(h * oran)), _Im.LANCZOS)
        tampon = io.BytesIO()
        g.save(tampon, format="JPEG", quality=82)
        return base64.b64encode(tampon.getvalue()).decode()
    except Exception:
        return ""


def _vision_model_ara(istemci, ayar) -> str:
    """Çok-modal modeli kademeli bul:
       1) ayarlar → modeller.goruntu_modeli elle seçildiyse doğrudan O,
       2) yüklü model adlarında vision/llava/minicpm-v/qwen.*vl izi,
       3) bulunamazsa '' (metin-only yol devam eder)."""
    elle = (ayar.get("modeller", {}) or {}).get("goruntu_modeli", "")
    if elle:
        return elle
    try:
        desen = re.compile(r"(vision|llava|minicpm.?v|moondream|qwen.*vl|"
                           r"glm.?4v|phi.?3.?vision)", re.I)
        for m in istemci.modelleri_tara():
            if desen.search(m.get("ad", "")):
                return m["ad"]
    except Exception:
        pass
    return ""


def _ollama():
    try:
        from cekirdek import yapilandirma
        from cekirdek.ollama_kontrol import OllamaIstemcisi
        ayar = yapilandirma.yukle()
        istemci = OllamaIstemcisi(ayar["ollama"]["adres"])
        if not istemci.canli_mi():
            return None, None
        model = (ayar["modeller"].get("rutin_model")
                 or (istemci.modelleri_tara() or [{}])[0].get("ad", ""))
        return istemci, model
    except Exception:
        return None, None


# ==================== HAFIZA KÖPRÜSÜ (göz ↔ bellek) ====================
def _hafiza_baglam(kelimeler: List[str]) -> List[str]:
    """Görseldeki anahtar kelimelerle hafızada geçmiş eşleşme ara.

    Bulunan satırlar analize bağlam olarak eklenir: 'bu hatayı daha önce
    görmüştün / bu uygulamayı sık kullanıyorsun'. Organ yoksa boş döner."""
    try:
        from cekirdek.gonderci import GONDERCI_BAGI
        hfz = GONDERCI_BAGI.get("hafiza")
        if hfz is None:
            return []
        bulunan: List[str] = []
        for kelime in kelimeler[:6]:
            for satir in hfz.ara(kelime)[:3]:
                s = satir.strip()[:220]
                if s and s not in bulunan:
                    bulunan.append(s)
        return bulunan[:8]
    except Exception:
        return []


def _bellek_notu(konu: str, olay: str):
    """Analiz sonucunu kalıcı belleğe tek satır işler — gözlem birikimi.

    Zaten benzer satır varsa tekrar yazmaz (kapıcının tercih satırlarıyla
    aynı bellek.md'yi paylaşır; çöp üretmemek için kısa + etiketli tutulur)."""
    cumle = f"[Ekran Gözü] {konu}: {olay}"[:200]
    try:
        from cekirdek.hafiza_kopru import tercih_kaydet
        return bool(tercih_kaydet(cumle))
    except Exception:
        try:
            from cekirdek.gonderci import GONDERCI_BAGI
            hfz = GONDERCI_BAGI.get("hafiza")
            if hfz is not None:
                hfz.kalici_ekle([cumle])
                return True
        except Exception:
            pass
    return False


def _onemli_kelimeler(metin: str) -> List[str]:
    """Hafıza araması için OCR metinden anlamlı anahtar kelimeleri süzer."""
    duragan = {"the", "and", "for", "with", "this", "that", "bir", "ve", "ile",
               "için", "bu", "şu", "not", "can", "will", "please"}
    kelimeler = [w.lower().strip(".,;:!?()[]{}\"'")
                 for w in re.split(r"\s+", metin or "")]
    return list(dict.fromkeys(w for w in kelimeler
                              if len(w) > 3 and w not in duragan))[:8]


def _cevir_anlat(metin: str, dil: str, soru: str = "",
                 gorsel=None, baglam_satirlari: List[str] | None = None) -> dict:
    """Metni Türkçe'ye çevirip kullanıcının anlayacağı biçimde açıkla.

    Model varsa: tek istem — 'çevir + ne istiyor + nasıl çözülür'.
    Gorsel verilirse ve çok-modal model bulunursa görsel de isteme eklenir
    (resim/diyagram/içerik yorumu); modal model yoksa yalnız metin gider.
    Baglam: hafızadan gelen geçmiş satırlar isteme 'BİLİNENLER' olarak konur.
    Model yoksa: yerel sözlük + kalıp eşleşmeli basit açıklama (yine de işe yarar).
    """
    istemci, model = _ollama()
    kullanci_soru = (soru or "").strip()
    if istemci and model:
        # çok-modal denemesi: ayarlarda ya da yüklü modellerde vision ara
        goruntu_modeli = ""
        gorsel_b64 = ""
        if gorsel is not None:
            try:
                from cekirdek import yapilandirma
                goruntu_modeli = _vision_model_ara(
                    istemci, yapilandirma.yukle())
                gorsel_b64 = _gorsel_b64(gorsel) if goruntu_modeli else ""
            except Exception:
                goruntu_modeli, gorsel_b64 = "", ""
        sistem = ("Sen ekrandaki metni okuyan bir yardımcısın. Kullanıcı Türkçe "
                  "bilmiyor olabilir. Gönderilen metni (her dilden) Türkçe'ye "
                  "çevir; sonra 2-4 maddeyle: bu neyi söylüyor/istiyor, olası "
                  "neden, kullanıcı ne yapmalı. Kısa ve somut yaz.")
        if gorsel_b64:
            sistem += (" Ekranda metin dışında resim/grafik/arayüz öğesi varsa "
                       "onları da betimle ve mesajın anlamıyla ilişkilendir.")
        baglam_metni = ""
        if baglam_satirlari:
            baglam_metni = ("\n\nBİLİNENLER (kullanıcının hafızasından — "
                            "geçmişte görülenler):\n"
                            + "\n".join("- " + b for b in baglam_satirlari))
        mesajlar = [{"role": "user", "content":
                     f"EKRAN METİNİ ({dil}):\n{metin[:2500]}\n\n"
                     + (f"KULLANICININ SORUSU: {kullanci_soru}" if kullanci_soru
                        else "Kullanıcı sadece ekranı gösterdi.") + baglam_metni}]
        # 1) modal modelle görselli dene (varsa) — başarısızsa sessizce düş
        if gorsel_b64:
            try:
                cevap = istemci.uretim(goruntu_modeli, mesajlar, sistem=sistem,
                                       gorseller=[gorsel_b64], zaman_asimi=180)
                if cevap:
                    return {"basarili": True, "model": goruntu_modeli,
                            "aciklama": cevap.strip(), "yontem": "modal-gorsel"}
            except Exception:
                pass
        try:
            cevap = istemci.uretim(model, mesajlar, sistem=sistem)
            if cevap:
                return {"basarili": True, "model": model,
                        "aciklama": cevap.strip(),
                        "yontem": "model+baglam" if baglam_satirlari else "model"}
        except Exception:
            pass
    # ---- yedek: yerel kalıp analizi (model/Ollama yoksa bile boş dönmez) ----
    satirlar = []
    if _hata_mi(metin):
        satirlar.append("Bu bir HATA mesajı gibi görünüyor.")
        kod = re.search(r"0x[0-9a-fA-F]{6,}", metin)
        if kod:
            aciklamalar = {"0x80070005": "Erişim engellendi (izin hatası) — "
                           "programı yönetici olarak çalıştır ya da dosya "
                           "izinlerini kontrol et.",
                           "0x80070002": "Dosya/başlangıç yolu bulunamadı."}
            satirlar.append(f"{kod.group(0)} → " +
                            aciklamalar.get(kod.group(0),
                                            "Windows hata kodu; internette "
                            f"'{kod.group(0)} hatası' arat."))
        if re.search(r"denied|permission|izin", metin, re.I):
            satirlar.append("İzin/erişim sorunu: dosya başka programda açık "
                            "olabilir veya yönetici izni gerekir.")
        yol = re.search(r"[A-Za-z]:\\[\w\\.\- ]+|\./[\w/\.\-]+", metin)
        if yol:
            satirlar.append(f"İlgili dosya/yol: {yol.group(0)}")
    elif dil == "zh":
        satirlar.append("Metin Çince — tam çeviri için Ollama modeli gerekli; "
                        "şimdilik anahtar kelimeler:")
        sozluk = {"无法": "yapılamaz/izin yok", "访问": "erişim",
                  "文件": "dosya", "权限": "yetki", "检查": "kontrol edin",
                  "设置": "ayarlar", "错误": "hata", "确定": "onay",
                  "取消": "iptal", "保存": "kaydet"}
        bulunan = {k: v for k, v in sozluk.items() if k in metin}
        satirlar.append(" · ".join(f"{k}={v}" for k, v in list(bulunan.items())[:8])
                        or "(sözlükte karşılık yok)")
    else:
        ilk = next((ln for ln in metin.splitlines() if len(ln.strip()) > 3), "")
        satirlar.append(f"Ekran metninin ilk satırı: \"{ilk[:160]}\"")
        satirlar.append("Anlamı için model destekli çeviri önerilir (Ollama).")
    return {"basarili": True, "model": "", "aciklama": "\n".join(satirlar),
            "yontem": "yerel-yedek"}


def _zihin_zinciri(metin: str, dil: str, soru: str, gorsel=None,
                   kaynak_bilgi: str = "") -> dict:
    """OKU→ANLA→ZİHİN ortak zinciri: hafıza bağlamı + çevir/açıkla + belleğe iade.

    1) OCR metninden anahtar kelimeler süzülür → hafızada geçmiş eşleşme aranır
       (bellek.md + oturum özetleri). Bulunan satırlar modele 'BİLİNENLER' gider.
    2) _cevir_anlat: modal model varsa görseli de görür; yoksa LLM metni işler;
       Ollama hiç yoksa yerel kalıp analizi devreye girer.
    3) Sonuç tek satır bellek notu olarak iade edilir — bir sonraki bakışta
       sistem bu olayı hatırlar ('zamanla kullanıcıyı tanıma').
    """
    kelimeler = _onemli_kelimeler(metin)
    baglam = _hafiza_baglam(kelimeler)
    sonuc = _cevir_anlat(metin, dil, soru, gorsel=gorsel,
                         baglam_satirlari=baglam)
    # ---- belleğe iade: kısa, etiketli gözlem notu ----
    tur = "hata mesajı" if _hata_mi(metin) else ("Çince metin" if dil == "zh"
                                                 else f"{dil} içerik")
    ilk = next((ln.strip() for ln in metin.splitlines() if len(ln.strip()) > 8), "")
    ozet_olay = f"{tur}: \"{ilk[:70]}\""
    yazildi = _bellek_notu((kaynak_bilgi or "ekran").strip()[:40], ozet_olay)
    yanit_parcalar = [
        f"Dil tahmini: {dil} · Okunan {len(metin)} karakter",
        (f"Hafızadan bağlam ({len(baglam)} kayıt):\n"
         + "\n".join("• " + b[:160] for b in baglam)) if baglam else "",
        "— ÖZET —\n" + metin[:400],
        f"— AÇIKLAMA ({sonuc['yontem']}) —\n" + sonuc["aciklama"],
        ("(Bu gözlem kalıcı belleğe yazıldı — bir dahakine hatırlanacak.)"
         if yazildi else ""),
    ]
    return {"basarili": True, "yanit": "\n".join(p for p in yanit_parcalar if p),
            "dil": dil, "okunan": metin[:1200],
            "aciklama": sonuc["aciklama"], "model": sonuc.get("model", ""),
            "yontem": sonuc.get("yontem", ""), "hafiza_baglami": baglam,
            "bellek_notu": ozet_olay, "not_yazildi": yazildi}


def eylem_oku_anla(soru: str = "", **s) -> dict:
    """Ekranı OKU ve ANLA: OCR → dil tespiti → Türkçe çeviri/açıklama → bellek.

    Kullanım: ekranda İngilizce/Çince metin ya da anlaşılmayan bir hata
    mesajı varsa bu eylem tek çağrıda hepsini yapar. İstersen 'soru' da
    ver: '{\"eylem\":\"oku_anla\",\"soru\":\"bu hatayı nasıl çözerim\"}'.
    Onay: goz_ekran (alan goz) — ilk kullanımda panelde kart çıkar."""
    izin = _izin_al("goz_ekran", "tam ekran (oku-anla)",
                    "Ekrandaki yazı okunup Türkçe'ye çevrilecek ve açıklanacak "
                    "(görsel diske yazılmaz; yalnızca kısa not belleğe eklenir).")
    if not izin.get("onayli"):
        return {"basarili": False, "yanit": "İzin verilmedi: " +
                (izin.get("neden") or izin.get("kaynak", ""))}
    kare = _kare_yakala()
    pencereler = _pencere_basliklari()
    if kare is None:
        return {"basarili": False,
                "yanit": "Ekran karesi alınamadı (headless/Pillow yok). "
                         "Masaüstü oturumda deneyin ya da bir PNG yoluyla "
                         "'gorsel_oku' kullanın.",
                "onay": izin["kaynak"]}
    oz = _analiz(kare, sinir=3000)
    metin = oz["metin"]
    if not metin:
        return {"basarili": True,
                "yanit": "Ekranda okunur metin bulunamadı. OCR dil paketlerini "
                         "kontrol edin (tesseract --list-langs). Açık pencere: "
                         + (", ".join(pencereler[:6]) or "?"),
                "onay": izin["kaynak"]}
    kaynak = ", ".join(pencereler[:3]) if pencereler else "ekran"
    z = _zihin_zinciri(metin, _dil_tespet(metin), soru, gorsel=kare,
                       kaynak_bilgi=kaynak)
    z["onay"] = izin["kaynak"]
    z["pencereler"] = pencereler[:8]
    return z


def eylem_zihin_analiz(gorsel_yol: str = "", konu: str = "",
                       soru: str = "", **s) -> dict:
    """Kullanıcının paylaştığı/gönderdiği GÖRSEL üzerinde derin analiz.

    Ekran görüntüsü dosyası, fotoğraf, PDF'den çevrilmiş PNG... Her neyse:
    OCR ile okur, hafızada konuyu/eşleşmeleri arar, modeli (varsa modal)
    devreye alır, sonucu belleğe not eder. 'konu' verilirse hafıza araması
    onunla zenginleştirilir. Bu, gözün 'beyinle konuşma' kapısıdır."""
    if not gorsel_yol:
        return {"basarili": False,
                "yanit": "Görsel yolu ver: zihin_analiz({\"gorsel_yol\":\"...png\","
                         "\"konu\":\"excel hatası\"})"}
    if not os.path.isfile(gorsel_yol):
        return {"basarili": False, "yanit": f"Dosya yok: {gorsel_yol}"}
    try:
        from PIL import Image
        gorsel = Image.open(gorsel_yol)
    except Exception as e:
        return {"basarili": False, "yanit": f"Görsel açılamadı: {e}"}
    oz = _analiz(gorsel, sinir=3000)
    metin = oz["metin"]
    ek_baglam = []
    if konu:
        ek_baglam = _hafiza_baglam(_onemli_kelimeler(konu))
    if not metin:
        # OCR boş döndü — en azından modal model denensin / renk ipucu verilsin
        dil = "bilinmeyen"
        sonuc = _cevir_anlat("(OCR metin üretemedi — görselde yazı yok olabilir)",
                             dil, soru or (konu or "Bu görselde ne var?"),
                             gorsel=gorsel, baglam_satirlari=ek_baglam)
        return {"basarili": True,
                "yanit": f"[{os.path.basename(gorsel_yol)}] OCR metin bulamadı.\n"
                         f"Renk/bölge: {oz['renk']}\n— MODEL YORUMU —\n"
                         + sonuc["aciklama"],
                "model": sonuc.get("model", ""), "yontem": sonuc.get("yontem", ""),
                "hafiza_baglami": ek_baglam}
    dil = _dil_tespet(metin)
    kelimeler = _onemli_kelimeler(metin) + _onemli_kelimeler(konu)
    baglam = _hafiza_baglam(list(dict.fromkeys(kelimeler)))
    sonuc = _cevir_anlat(metin, dil, soru, gorsel=gorsel,
                         baglam_satirlari=baglam)
    tur = "hata mesajı" if _hata_mi(metin) else ("Çince metin" if dil == "zh"
                                                 else f"{dil} içerik")
    konu_etiket = (konu or os.path.basename(gorsel_yol))[:40]
    ilk = next((ln.strip() for ln in metin.splitlines() if len(ln.strip()) > 8), "")
    yazildi = _bellek_notu(konu_etiket, f"{tur}: \"{ilk[:70]}\"")
    parcalar = [f"[{os.path.basename(gorsel_yol)}] Dil: {dil}",
                (f"Hafıza eşleşmeleri:\n"
                 + "\n".join("• " + b[:160] for b in baglam)) if baglam else "",
                "— GÖRSELDEN OKUNAN —\n" + metin[:400],
                f"— ZEHİN ANALİZİ ({sonuc['yontem']}"
                + (f" · model: {sonuc['model']}" if sonuc.get("model") else "")
                + ") —\n" + sonuc["aciklama"],
                ("(Not belleğe eklendi.)" if yazildi else "")]
    return {"basarili": True, "yanit": "\n".join(p for p in parcalar if p),
            "dil": dil, "okunan": metin[:1200], "aciklama": sonuc["aciklama"],
            "model": sonuc.get("model", ""), "yontem": sonuc.get("yontem", ""),
            "hafiza_baglami": baglam, "not_yazildi": yazildi}


def eylem_ekran_oku(soru: str = "", **s) -> dict:
    """GÖZ'ün 'anlama' zinciri: yakala → OCR → dil tespiti → çevir+açıkla.

    Onay: goz_ekran (alan goz) — panel kartı çıkar; panel yanıt vermezse
    sohbet üzerinden 'evet/hayır' sorulabilir (/api/sohbet_onay ile)."""
    izin = _izin_al("goz_ekran", "tam ekran (okuma)",
                    "Ekrandaki yazı okunup Türkçe'ye çevrilecek "
                    "(görsel diske yazılmaz, yalnız metin işlenir).")
    if not izin.get("onayli"):
        return {"basarili": False, "yanit": "İzin verilmedi: " +
                (izin.get("neden") or izin.get("kaynak", ""))}
    kare = _kare_yakala()
    if kare is None:
        return {"basarili": False,
                "yanit": "Ekran karesi alınamadı (headless/Pillow yok). "
                         "Masaüstü oturumda deneyin."}
    oz = _analiz(kare, sinir=3000)
    metin = oz["metin"]
    if not metin:
        return {"basarili": True,
                "yanit": "Ekranda okunur metin bulunamadı. OCR dil paketlerini "
                         "kontrol edin (tesseract --list-langs)."}
    z = _zihin_zinciri(metin, _dil_tespet(metin), soru, gorsel=kare,
                       kaynak_bilgi=", ".join(_pencere_basliklari()[:3]))
    z["onay"] = izin["kaynak"]
    return z


def eylem_gorsel_oku(yol: str = "", soru: str = "", **s) -> dict:
    """Kullanıcının verdiği PNG/JPG üzerinde aynı zincir (paylaşılan ekran
    görüntüsü, telefon fotoğrafı vb.). Dosya okuma serbesttir; içeriği
    dışarıya gitmez — iş yerelde (OCR) + model varsa Ollama'da yapılır."""
    if not yol:
        return {"basarili": False, "yanit": "Görsel yolu ver: gorsel_oku({\"yol\":\"C:\\...png\"})"}
    if not os.path.isfile(yol):
        return {"basarili": False, "yanit": f"Dosya yok: {yol}"}
    try:
        from PIL import Image
        gorsel = Image.open(yol)
    except Exception as e:
        return {"basarili": False, "yanit": f"Görsel açılamadı: {e}"}
    oz = _analiz(gorsel, sinir=3000)
    metin = oz["metin"]
    if not metin:
        return {"basarili": True,
                "yanit": "Görselde okunur metin yok — içinde resim/çizim var "
                         "demek. Betimleme için çok-modal model gerekir "
                         "(ör. llava); maliyet için önce OCR'lı metin tercih edilir."}
    z = _zihin_zinciri(metin, _dil_tespet(metin), soru, gorsel=gorsel,
                       kaynak_bilgi=os.path.basename(yol))
    return z


# ==================== NÖBETÇİ + HAFIZA KÖPRÜSÜ ====================
def eylem_raporlari_besle(**s) -> dict:
    """Nöbetçi raporlarını hafıza organına besler: hangi pencerede yoğunlaşma
    var → 'kullanıcı X penceresinde yoğunlaşıyor → tercih güncelle'."""
    raporlar = list(_nobet["rapor"])
    if not raporlar:
        return {"basarili": True, "yanit": "Biriktirilmiş nöbetçi raporu yok."}
    sayac: Dict[str, int] = {}
    for r in raporlar:
        for p in r.get("pencereler", [])[:4]:
            anahtar = p.split(" - ")[0][:40]
            sayac[anahtar] = sayac.get(anahtar, 0) + 1
    sirali = sorted(sayac.items(), key=lambda x: -x[1])[:3]
    cumleler = [f"Kullanıcı {ad} penceresinde yoğunlaşıyor "
                f"({adet}/{len(raporlar)} gözlem)." for ad, adet in sirali]
    try:
        from cekirdek.hafiza_kopru import tercih_kaydet
        kabul = sum(1 for c in cumleler if tercih_kaydet(c))
    except Exception:
        kabul = 0
    return {"basarili": True,
            "yanit": (f"{len(raporlar)} nöbetçi raporu işlendi. "
                      f"{kabul} tercih cümlesi kalıcı belleğe yazıldı:\n"
                      + "\n".join("• " + c for c in cumleler)),
            "tercihler": cumleler}


# ==================== ANLIK EKRAN GÖRÜNTÜSÜ (panel butonu) ====================
try:                                  # sistem içinde yüklüyse çekirdek yolu kullan
    from cekirdek import yapilandirma as _yp
    GORUNTU_DIZIN = os.path.join(_yp.VERI_DIZIN, "ekran_goruntuleri")
except Exception:                     # node tek başına test ediliyorsa yerel yol
    GORUNTU_DIZIN = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "veri", "ekran_goruntuleri")


def eylem_goruntu_kaydet(**s) -> dict:
    """İstenen anda tam ekranı PNG olarak diske yazar (kullanıcı butonu).

    Onay: goz_kayit (alan goz) — her kayıt sorulur; 'oturum' seçilirse bir
    daha sorulmaz. Dosya adı zaman damgalıdır."""
    izin = _izin_al("goz_kayit", "ekran görüntüsü kaydı",
                    "Ekranın şu anki görüntüsü PNG olarak veri klasörüne "
                    "kaydedilecek.")
    if not izin.get("onayli"):
        return {"basarili": False, "yanit": "İzin verilmedi: " +
                (izin.get("neden") or izin.get("kaynak", ""))}
    kare = _kare_yakala()
    if kare is None:
        return {"basarili": False,
                "yanit": "Ekran karesi alınamadı (headless/Pillow yok)."}
    try:
        os.makedirs(GORUNTU_DIZIN, exist_ok=True)
        ad = time.strftime("ekran_%Y%m%d_%H%M%S.png")
        yol = os.path.join(GORUNTU_DIZIN, ad)
        kare.save(yol)
        boyut_kb = round(os.path.getsize(yol) / 1024, 1)
        oz = _analiz(kare, sinir=300)
        return {"basarili": True, "yol": yol, "boyut_kb": boyut_kb,
                "yanit": f"📷 Ekran görüntüsü kaydedildi: {yol} ({boyut_kb} KB)"
                         + (f"\nOkunan metin: {oz['metin'][:200]}..." if oz["metin"] else ""),
                "onay": izin["kaynak"]}
    except Exception as e:
        return {"basarili": False, "yanit": f"Kayıt hatası: {e}"}


def eylem_goruntuler(**s) -> dict:
    """Son kaydedilen ekran görüntüleri (panel önizleme için)."""
    liste = []
    try:
        for ad in sorted(os.listdir(GORUNTU_DIZIN), reverse=True)[:20]:
            if ad.endswith(".png"):
                liste.append({"ad": ad,
                              "url": "/statik/goruntu/" + ad,
                              "kb": round(os.path.getsize(
                                  os.path.join(GORUNTU_DIZIN, ad)) / 1024, 1)})
    except Exception:
        pass
    return {"basarili": True, "goruntuler": liste,
            "yanit": f"{len(liste)} görüntü: " +
                     ", ".join(x["ad"] for x in liste[:5])}


_EYLEMLER = {
    "izleme_durumu": eylem_izleme_durumu,
    "ekran_tara": eylem_ekran_tara,
    "oku_anla": eylem_oku_anla,
    "zihin_analiz": eylem_zihin_analiz,
    "ekran_oku": eylem_ekran_oku,
    "gorsel_oku": eylem_gorsel_oku,
    "pencere_tara": eylem_pencere_tara,
    "bolum_tara": eylem_bolum_tara,
    "gozetle": eylem_gozetle,
    "durdur": eylem_durdur,
    "raporlari_besle": eylem_raporlari_besle,
    "goruntu_kaydet": eylem_goruntu_kaydet,
    "goruntuler": eylem_goruntuler,
}


def calistir(metin: str, **saglama) -> dict:
    """JSON ya da düz Türkçe komutla çağrılır."""
    t = str(metin or "").strip()
    girdi: Dict[str, object] = {}
    if t.startswith("{"):
        try:
            girdi = json.loads(t)
        except Exception:
            girdi = {}
    else:
        alt = t.lower()
        if any(k in alt for k in ("oku ve anla", "ekranı oku", "yazıyı çevir",
                                   "çevir", "hata mesajı", "ne diyor",
                                   "ne yazıyor", "anlamını")):
            girdi = {"eylem": "oku_anla", "soru": t}
        elif any(k in alt for k in ("görseli analiz", "resmi yorumla",
                                     "bu resim", "zihin analizi")):
            yol = re.search(r"[\w\\/\-\.]+\.(png|jpe?g|bmp|webp)", t, re.I)
            girdi = {"eylem": "zihin_analiz",
                     **({"gorsel_yol": yol.group(0)} if yol else {}),
                     "konu": t}
        elif any(k in alt for k in ("gözle", "ekrana bak", "şu an ne", "ne var", "tara")):
            girdi = {"eylem": "ekran_tara"}
        elif "nöbet" in alt or "gözetle" in alt or "izleme başlat" in alt:
            girdi = {"eylem": "gozetle"}
        elif "durdur" in alt or "kapat" in alt:
            girdi = {"eylem": "durdur"}
        elif "durum" in alt or "hangi araç" in alt:
            girdi = {"eylem": "izleme_durumu"}
        else:
            girdi = {"eylem": "ekran_tara"}
    eylem = str(girdi.pop("eylem", "ekran_tara"))
    fonk = _EYLEMLER.get(eylem)
    if not fonk:
        return {"basarili": False,
                "yanit": f"Bilinmeyen göz eylemi '{eylem}'. Geçerliler: "
                         + ", ".join(sorted(_EYLEMLER)), "eylem": eylem}
    sonuc = fonk(**girdi)
    sonuc["eylem"] = eylem
    return sonuc


sozlesme = {
    "kod": "ekran_gozu",
    "ad": "Ekran Gözü (Ucuz Ekran Gözlemi + Oku-Anla-Zihin)",
    "tur": "node",
    "surum": "0.2",
    "aciklama": "Ekrana bakar: tam ekran karesi + pencere listesi + OCR; "
                "değişim-piksel nöbetçisi ile ucuz sürekli gözlem. OKU-ANLA "
                "zinciri: İngilizce/Çince metin ve hata mesajlarını Türkçe'ye "
                "çevirip açıklar; görsel varsa modal modelle yorumlar; her "
                "gözlem hafıza organına not edilir (önce hafıza aranır). "
                "Bulut/GPU yok.",
    "gorev_anahtarlari": ["ekran", "göz", "gözlem", "pencere", "scr",
                          "ekrana bak", "şu an ne var", "gözetle", "ocr",
                          "ekranı oku", "oku ve anla", "hata mesajı",
                          "yazıyı çevir", "ne diyor", "ingilizce metin",
                          "çince metin", "resmi yorumla", "görsel analiz",
                          "ekrandaki yazı"],
    "cagri_ornekleri": [
        "'ekrana bak şu an ne var' → ekran_gozu(\"ekran_tara\")",
        "'chrome penceresini tara' → ekran_gozu({\"eylem\":\"pencere_tara\","
        "\"baslik\":\"chrome\"})",
        "'ekranı 30 sn'de bir gözetle' → ekran_gozu({\"eylem\":\"gozetle\","
        "\"sure_sn\":30})",
        "'ekrandaki hatayı oku anla' → ekran_gozu({\"eylem\":\"oku_anla\","
        "\"soru\":\"nasıl çözerim\"}) — OCR+çeviri+açıklama+hafıza tek çağrıda",
        "'bu resmi yorumla C:\\Users\\a\\masa.png' → ekran_gozu({\"eylem\":"
        "\"zihin_analiz\",\"gorsel_yol\":\"...png\",\"konu\":\"excel hatası\"})"
        " — hafıza eşleşmeli derin analiz"],
    "calistir": calistir,
}
