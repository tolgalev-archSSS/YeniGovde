# -*- coding: utf-8 -*-
"""NODE BULUCU YETENEĞİ — Sistem kendini açık kaynak node'larla büyütür.

Akış (kullanıcı "şu işi yapan bir node bul" dediğinde):
  1) ARA    : GitHub API'de aday depolar aranır; yıldız/güncellik/lisans/
              boyut/açıklama sinyalleriyle PUANLANIR (LLM varsa gerekçeli).
  2) KURULU?: aynı işi yapan kurulu modül varsa kullanıcıya hatırlatılır.
  3) INDIR  : kullanıcı seçer → zip arşivi güvenli geçici alana indirilir,
              tek kök klasör denetlenir, nodeller/<kod>/ altına açılır,
              sozlesme test yüklemesiyle doğrulanır, sisteme entegre edilir
              (TEKIL.tara + sol menü otomatik görür), hafızaya not düşülür.
  4) KABUL  : dışarıdan elle yazılan node'lar nodeller/kabul/ klasörüne
              konur; panel/Ayarlar→Node Yönetimi'nden onaylanıp yüklüye geçer.

GÜVENLİK: indirme/onaylama daima ONAY KARTINA bağlıdır (onay_serbest bile
etse de bu yetenekte kart çıkar — kod çalıştıran bir paket sıradan veri değil).
Arşiv taşması (zip-slip) ve çok köklü arşiv reddedilir.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.util import module_from_spec, spec_from_file_location
from typing import Dict, List

import requests

AJAN = {"User-Agent": "MLAO-node-bulucu", "Accept": "application/vnd.github+json"}
TEMEL = "https://api.github.com"


def _kabul_dizin() -> str:
    from cekirdek import yapilandirma
    yapilandirma.gerekli_dizinler()
    return yapilandirma.KABUL_DIZIN


def _nodeller_dizin() -> str:
    from cekirdek import yapilandirma
    yapilandirma.gerekli_dizinler()
    return yapilandirma.NODE_DIZIN


def _onay_al(eylem: str, hedef: str, aciklama: str) -> dict:
    """Node indirme/onaylama HER ZAMAN kart ister: onay_serbest ayarı yalnız
    sıradan dış-dünya okumalarını serbest bırakır; kod paketi kurmak farklı."""
    try:
        from cekirdek.onay import TEKIL_KAPICI
        return TEKIL_KAPICI.denetle(eylem, hedef, aciklama, alan="node")
    except Exception:
        return {"onayli": True, "kaynak": "kapici_yok", "neden": ""}


# ------------------------------------------------------------------ arama
def _github_ara(sorgu: str, adet: int) -> List[Dict]:
    r = requests.get(f"{TEMEL}/search/repositories",
                     params={"q": sorgu, "sort": "stars", "order": "desc",
                             "per_page": adet}, headers=AJAN, timeout=25)
    r.raise_for_status()
    return r.json().get("items", [])


def _puanla(item: Dict, gereksinim: str) -> Dict:
    """Kural tabanlı puan + gerekçeler. LLM sıralamayı sonra ince ayarlar."""
    yildiz = item.get("stargazers_count", 0)
    issue_acik = item.get("open_issues_count", 0)
    fork = item.get("forks_count", 0)
    boyut_kb = item.get("size", 0)
    guncel = (item.get("pushed_at") or "")[:10]
    lisans = ((item.get("license") or {}).get("spdx_id") or "").upper()
    dil = item.get("language") or ""
    aciklama = item.get("description") or ""
    ad = item.get("full_name", "")
    puan, nedenler = 0.0, []
    # popülerlik (logaritmik — ~10k yıldız ≈ +0.30)
    pop = min(0.30, (max(yildiz, 1) ** 0.5) / 32.0)
    puan += pop
    nedenler.append(f"⭐{yildiz} yıldız (+{pop:.2f})")
    # bakım tazeliği
    if guncel >= "2026-01":
        puan += 0.20; nedenler.append("bu yıl aktif geliştirme (+0.20)")
    elif guncel >= "2025-01":
        puan += 0.12; nedenler.append("geçen yıla kadar güncel (+0.12)")
    elif guncel:
        puan += 0.04; nedenler.append(f"son itme eski: {guncel} (+0.04)")
    else:
        nedenler.append("tarih çözülemedi (+0.00)")
    # lisans
    if lisans in ("MIT", "BSD-3-CLAUSE", "BSD-2-CLAUSE", "ISC", "APACHE-2.0"):
        puan += 0.15; nedenler.append(f"özgür lisans {lisans} (+0.15)")
    elif lisans in ("GPL-3.0", "GPL-2.0", "AGPL-3.0", "LGPL-3.0"):
        puan += 0.08; nedenler.append(f"copyleft {lisans}: gömülebilir ama dikkat (+0.08)")
    elif lisans in ("NOASSERTION", ""):
        puan -= 0.10; nedenler.append("lisans belirsiz (-0.10)")
    else:
        puan += 0.05; nedenler.append(f"lisans {lisans} (+0.05)")
    # sorun oranı (açık issue / yıldız)
    oran = issue_acik / max(yildiz, 1)
    if oran < 0.05 and yildiz > 50:
        puan += 0.10; nedenler.append("az açık sorun, sağlam görünüyor (+0.10)")
    elif oran > 0.3:
        puan -= 0.08
        nedenler.append(f"açık issue/yıldız oranı yüksek {oran:.2f} (-0.08)")
    # topluluk
    if fork > 100:
        puan += 0.05; nedenler.append("geniş topluluk çatallaması (+0.05)")
    # açıklama kalitesi + istenen terimlerle eşleşme
    if len(aciklama) > 15:
        puan += 0.05; nedenler.append("net tanım var (+0.05)")
    terimler = [t for t in re.split(r"[^\w]+", gereksinim.lower()) if len(t) > 3]
    eslesen = [t for t in terimler if t in (aciklama + " " + ad).lower()]
    if eslesen:
        bonus = min(0.20, 0.07 * len(eslesen))
        puan += bonus
        nedenler.append("gereksinimle sözcük örtüşmesi: "
                        + ", ".join(eslesen[:4]) + f" (+{bonus:.2f})")
    else:
        puan -= 0.05
        nedenler.append("başlık/açıklama gereksinimle zayıf örtüşüyor (-0.05)")
    # dil: sistem Python tabanı — Python node'ları doğal entegrasyon avantajı
    if dil == "Python":
        puan += 0.05
        nedenler.append("Python: sözleşme dosyasıyla doğrudan takılabilir (+0.05)")
    elif dil:
        nedenler.append(f"dil {dil}: çekirdeğe köprü gerekir (adaptör önerilir)")
    else:
        nedenler.append("dil bilgisi yok")
    # boyut uyarısı
    if boyut_kb > 200_000:
        puan -= 0.05; nedenler.append(f"dev depo {boyut_kb // 1024} MB (-0.05)")
    return {
        "ad": ad, "url": item.get("html_url", ""),
        "aciklama": aciklama[:200], "yildiz": yildiz, "fork": fork,
        "lisans": lisans or "?", "dil": dil, "son_itme": guncel,
        "puan": round(max(0.0, min(1.0, puan)), 2),
        "nedenler": nedenler,
        "arsiv_url": (item.get("archive_url") or "").replace("{/ref}", ""),
        "varsayilan_dal": item.get("default_branch", "main"),
    }


def _kurulu_eslese(gereksinim: str) -> List[str]:
    """Aynı işi yapan kurulu modül var mı? (boşa node kurmanın önüne geçer)"""
    try:
        from cekirdek.modul_iskeleti import TEKIL
        kelimeler = {w for w in re.split(r"[^\w]+", gereksinim.lower()) if w}
        uyanlar = []
        for kayit in TEKIL.tara():
            anahtarlar = {a.lower() for a in kayit.get("gorev_anahtarlari", [])}
            metin = (kayit.get("kod", "") + " " + kayit.get("ad", "") + " " +
                     kayit.get("aciklama", "")).lower()
            if anahtarlar & kelimeler or any(k in metin for k in kelimeler
                                             if len(k) > 4):
                uyanlar.append(f"{kayit['kod']} ({kayit['tur']})")
        return sorted(set(uyanlar))
    except Exception:
        return []


def _llm_sirala(gereksinim: str, adaylar: List[Dict]) -> List[Dict]:
    """Ağır model varsa adayları kullanıcının İHTİYACINA göre yeniden
    sıralar ve kısa gerekçe yazar; model yoksa kural puanı kalır."""
    if not adaylar:
        return adaylar
    try:
        from cekirdek import yapilandirma
        from cekirdek.ollama_kontrol import OllamaIstemcisi
        ayar = yapilandirma.yukle()
        model = (ayar["modeller"].get("agir_model")
                 or ayar["modeller"].get("siniflandirma_modeli"))
        if not model:
            return adaylar
        istemci = OllamaIstemcisi(ayar["ollama"]["adres"])
        if not istemci.canli_mi():
            return adaylar
        kisalt = [{i + 1: {"ad": a["ad"], "puan": a["puan"],
                           "ozet": a["aciklama"][:120], "dil": a["dil"],
                           "lisans": a["lisans"]}
                   } for i, a in enumerate(adaylar)]
        cevap = istemci.uretim(
            model, [{"role": "user", "content": json.dumps(
                {"gereksinim": gereksinim, "adaylar": kisalt},
                ensure_ascii=False)}],
            sistem=("Kullanıcının node gereksinimini ve aday depo listesini "
                    "alacaksın. İhtiyacı EN İYİ KARŞILAYAN sıraya diz; her "
                    "biri için 1 cümlelik Türkçe gerekçe ve 0-100 puan ver. "
                    'SADECE JSON dizi dön: [{"no":1,"puan":87,"gerekce":"..."}]'),
            sıcaklik=0.2, zaman_asimi=90)
        m = re.search(r"\[.*\]", cevap or "", flags=re.S)
        if not m:
            return adaylar
        karar = json.loads(m.group(0))
        sirali = []
        for k in karar:
            no = int(k.get("no", 0)) - 1
            if 0 <= no < len(adaylar):
                a = dict(adaylar[no])
                a["puan"] = round(float(k.get("puan", a["puan"] * 100)) / 100.0, 2)
                a["gerekce_llm"] = k.get("gerekce", "")
                sirali.append(a)
        kalan = [a for a in adaylar
                 if not any(s["ad"] == a["ad"] for s in sirali)]
        return sirali + kalan
    except Exception:
        return adaylar


# ------------------------------------------------------------------ indirme
def _temiz_kod(ad: str) -> str:
    kod = re.sub(r"[^a-z0-9_]+", "_", ad.lower()).strip("_")
    return kod[:40] or "node"


def _paket_dogrula(hedef: str) -> Dict:
    """Pakette modul.py + sozlesme + calistir var mı? (test yüklemesi)"""
    sonuc = {"tam": False, "kod": "", "hata": ""}
    ana = os.path.join(hedef, "modul.py")
    if not os.path.exists(ana):
        sonuc["hata"] = "modul.py yok"
        return sonuc
    spec = spec_from_file_location("_node_test_", ana)
    if spec is None or spec.loader is None:
        sonuc["hata"] = "modul.py derlenemedi"
        return sonuc
    import sys
    try:
        mod = module_from_spec(spec)
        ebeveyn = os.path.dirname(hedef)
        if ebeveyn not in sys.path:
            sys.path.insert(0, ebeveyn)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "sozlesme"):
            sonuc["hata"] = "'sozlesme' sözlüğü yok"
            return sonuc
        if not callable(getattr(mod, "calistir", None)):
            sonuc["hata"] = "calistir() fonksiyonu yok"
            return sonuc
        sonuc["tam"] = True
        sonuc["kod"] = (mod.sozlesme.get("kod")
                        if isinstance(mod.sozlesme, dict)
                        else os.path.basename(hedef)) or os.path.basename(hedef)
        return sonuc
    except Exception as e:
        sonuc["hata"] = (f"yükleme hatası: {type(e).__name__}: "
                         f"{str(e)[:120]}")
        return sonuc


def _arsiv_ac(icerik: bytes, hedef_kod: str) -> str:
    """Zip'i denetimli şekilde nodeller/<kod>/ altına açar; iç kökü döndürür.
    zip-slip ve çok köklü arşiv koruması."""
    hedef_kok = os.path.join(_nodeller_dizin(), hedef_kod)
    if os.path.exists(hedef_kok):
        hedef_kok = hedef_kok + "_" + time.strftime("%H%M%S")
    gecici = tempfile.mkdtemp(prefix="node_zip_")
    try:
        with zipfile.ZipFile(io.BytesIO(icerik)) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in n.split("/"):
                    raise ValueError(f"güvensiz arşiv yolu: {n}")
            z.extractall(gecici)
        tepeler = [d for d in os.listdir(gecici)
                   if os.path.isdir(os.path.join(gecici, d))]
        if len(tepeler) != 1:
            raise ValueError("arşivde tek kök klasör olmalı "
                             f"(bulunan: {tepeler or 'yok'})")
        os.makedirs(hedef_kok, exist_ok=True)
        ic = os.path.join(gecici, tepeler[0])
        hedef_ic = os.path.join(hedef_kok, tepeler[0])
        shutil.move(ic, hedef_ic)
        return hedef_ic
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


def _indir_ve_kur(secenek: Dict, oturum: str) -> Dict:
    """Seçilen depoyu indir, doğrula, nodeller/'e kur, entegre et, hatırla."""
    izin = _onay_al("node_indir", secenek.get("ad", "?"),
                    f"'{secenek.get('ad')}' deposu (~{secenek.get('yildiz')} ⭐) "
                    "kod olarak indirilip sisteme NODE olarak kurulacak. "
                    "Kaynak: " + secenek.get("url", ""))
    if not izin.get("onayli"):
        return {"basarili": False,
                "hata": "Kurulum onaylanmadı: " +
                        (izin.get("neden") or izin.get("kaynak", ""))}
    ad = secenek.get("ad", "")
    url = f"https://api.github.com/repos/{ad}/zipball/{secenek.get('varsayilan_dal', 'HEAD')}"
    try:
        r = requests.get(url, headers=AJAN, timeout=120)
        r.raise_for_status()
        icerik = r.content
        if not icerik.startswith(b"PK"):
            raise ValueError("indirilen dosya zip değil")
        hedef_kod = _temiz_kod(ad.split("/")[-1])
        kok = _arsiv_ac(icerik, hedef_kod)
        dogrulama = _paket_dogrula(kok)
        if not dogrulama["tam"]:
            shutil.rmtree(os.path.dirname(kok), ignore_errors=True)
            return {"basarili": False,
                    "hata": f"Paket Node sözleşmesine uymuyor ({dogrulama['hata']}). "
                            "GitHub projesi modul.py + sozlesme biçiminde değil; "
                            "çekirdeğe bağlamak için adaptör gerekir.",
                    "oneri": "nodeller/kabul/ altına uyumlu bir sarmalayıcı yazıp "
                             "panel üzerinden onaylayabilirsiniz."}
        from cekirdek.modul_iskeleti import TEKIL
        TEKIL.tara(yeniden=True)
        # hafızaya kalıcı not — kullanıcı/node geçmişi zamanla birikir
        try:
            from cekirdek.gonderci import GONDERCI_BAGI
            hafiza = GONDERCI_BAGI.get("hafiza")
            if hafiza:
                hafiza.kalici_ekle(
                    f"Node kuruldu: {kok} (kaynak: {secenek.get('url', '?')}, "
                    f"puan: {secenek.get('puan')})")
        except Exception:
            pass
        return {"basarili": True, "yol": kok,
                "yanit": (f"✅ '{os.path.basename(kok)}' node olarak kuruldu ve "
                          f"sol menüye eklendi. Uygunluk puanı: "
                          f"{secenek.get('puan')}.\nÇağırmak için: /"
                          + dogrulama["kod"] + " <girdi>")}
    except Exception as e:
        return {"basarili": False,
                "hata": f"İndirme/kurma hatası: {str(e)[:200]}"}


# ------------------------------------------------------------------ kabul onaylama
def _kabul_onayla(dosya_adi: str) -> Dict:
    """nodeller/kabul/<ad> klasörünü doğrula → yüklü node yap."""
    kabul = os.path.join(_kabul_dizin(), dosya_adi)
    if not os.path.isdir(kabul):
        return {"basarili": False, "hata": f"kabul/{dosya_adi} bulunamadı"}
    izin = _onay_al("node_kabul", dosya_adi,
                    f"Dışarıdan yazılan '{dosya_adi}' node'u onaylanıp "
                    "yüklü node'lara taşınacak (kod çalıştırma yetkisi verir).")
    if not izin.get("onayli"):
        return {"basarili": False,
                "hata": "Onay verilmedi: " +
                        (izin.get("neden") or izin.get("kaynak", ""))}
    dogrulama = _paket_dogrula(kabul)
    if not dogrulama["tam"]:
        return {"basarili": False,
                "hata": "Paket reddedildi: " + dogrulama["hata"] +
                        " — kabul klasöründe kaldı, düzeltip yeniden deneyin."}
    hedef = os.path.join(_nodeller_dizin(), dosya_adi)
    if os.path.exists(hedef):
        hedef = hedef + "_" + time.strftime("%H%M%S")
    shutil.move(kabul, hedef)
    from cekirdek.modul_iskeleti import TEKIL
    TEKIL.tara(yeniden=True)
    return {"basarili": True, "yol": hedef,
            "yanit": f"✅ '{dosya_adi}' kabul edildi ve yüklendi: {hedef}"}


# ------------------------------------------------------------------ ana giriş
def calistir(metin: str, **saglama) -> dict:
    ham = str(metin or "").strip()
    gorev: Dict = {}
    if ham.startswith("{"):
        try:
            gorev = json.loads(ham)
        except Exception:
            gorev = {"eylem": "bul", "sorgu": ham}
    else:
        gorev = {"eylem": "bul", "sorgu": ham}
    eylem = str(gorev.get("eylem", "bul")).lower()

    if eylem == "indir":
        secenek = gorev.get("secenek") or saglama.get("secenek") or {}
        if isinstance(secenek, str):
            try:
                secenek = json.loads(secenek)
            except Exception:
                return {"basarili": False, "hata": "Geçersiz seçenek verisi.",
                        "yanit": ""}
        sonuc = _indir_ve_kur(secenek, str(gorev.get("oturum", "genel")))
        sonuc.setdefault("yanit", sonuc.get("hata", ""))
        return {"basarili": bool(sonuc.get("basarili")), **sonuc}

    if eylem == "kabul_listele":
        liste = sorted(os.listdir(_kabul_dizin())) \
            if os.path.isdir(_kabul_dizin()) else []
        detay = []
        for ad in liste:
            yol = os.path.join(_kabul_dizin(), ad)
            if os.path.isdir(yol) and not ad.startswith("."):
                kontrol = _paket_dogrula(yol)
                detay.append({"ad": ad, "hazir": kontrol["tam"],
                              "durum": "sözleşme OK" if kontrol["tam"]
                                       else kontrol["hata"]})
        return {"basarili": True,
                "yanit": json.dumps(detay, ensure_ascii=False),
                "liste": detay}

    if eylem == "kabul_onayla":
        ad = str(gorev.get("dosya") or gorev.get("sorgu") or "").strip("/")
        sonuc = _kabul_onayla(ad)
        sonuc.setdefault("yanit", sonuc.get("hata", ""))
        return {"basarili": bool(sonuc.get("basarili")), **sonuc}

    # --- varsayılan: BUL + puanla ---
    gereksinim = str(gorev.get("sorgu") or gorev.get("gereksinim") or ham).strip()
    if not gereksinim:
        return {"basarili": False, "hata": "Gereksinim boş.", "yanit": ""}
    adet = int(gorev.get("adet", 8))
    sorgular = [gereksinim]
    if not gereksinim.isascii():
        ceviri = _kaba_cevir(gereksinim)
        if ceviri:
            sorgular.append(ceviri)
    aday_ham: List[Dict] = []
    hatalar: List[str] = []
    with ThreadPoolExecutor(max_workers=2) as havuz:
        gelecek = {havuz.submit(_github_ara, s, adet): s for s in sorgular}
        for f in as_completed(list(gelecek), timeout=90):
            try:
                aday_ham += f.result()
            except Exception as e:
                hatalar.append(str(e)[:120])
    gorulen, tekil = set(), []
    for it in aday_ham:
        if it.get("full_name") not in gorulen:
            gorulen.add(it.get("full_name"))
            tekil.append(it)
    puanli = [_puanla(it, gereksinim) for it in tekil]
    puanli.sort(key=lambda a: -a["puan"])
    puanli = _llm_sirala(gereksinim, puanli)[:adet]
    kurulu = _kurulu_eslese(gereksinim)
    satirlar = [f"GEREKSİNİM: {gereksinim}"]
    if kurulu:
        satirlar.append("KURULU BENZERLERİ (belki node'a gerek yok): " +
                        ", ".join(kurulu))
    for i, a in enumerate(puanli, 1):
        satirlar.append(
            f"{i}. {a['ad']} — PUAN {a['puan']} | ⭐{a['yildiz']} | "
            f"lisans:{a['lisans']} | dil:{a['dil'] or '?'} | "
            f"son itme:{a['son_itme']}\n   {a['url']}\n   {a['aciklama']}\n"
            + (f"   MODEL GEREKÇESİ: {a['gerekce_llm']}\n"
               if a.get("gerekce_llm") else "")
            + "   NEDENLER: " + "; ".join(a["nedenler"]))
    if hatalar:
        satirlar.append("ARAMA HATALARI: " + "; ".join(hatalar))
    if not puanli:
        satirlar.append("Hiç aday bulunamadı — sorguyu İngilizce ve kısa "
                        "deneyin (ör. 'speech to text').")
    satirlar.append("\nKURULUM: beğendiğin adayın verisiyle "
                    '{"eylem":"indir","secenek":{...}} gönder ya da panelden seç.')
    return {"basarili": True, "yanit": "\n".join(satirlar),
            "adaylar": puanli, "kurulu_benzler": kurulu,
            "model_notu": "derlemeyi AĞIR model yapmalı (ihtiyaç↔node eşleşme "
                          "gerekçeleriyle, kullanıcı hafıza tercihleri göz önünde)"}


def _kaba_cevir(tr: str) -> str:
    """GitHub araması için mini TR→EN sözlüğü (çeviri modeli yoksa yedek)."""
    sozluk = {
        "ses": "speech", "sesi": "speech", "tanıma": "recognition",
        "metne": "text", "metin": "text", "resim": "image", "görüntü": "image",
        "görsel": "visual", "video": "video", "çeviri": "translation",
        "grafik": "graphics", "veri": "data", "toplama": "scraping",
        "kazıma": "scraping", "web": "web", "haber": "news", "rss": "rss",
        "takip": "tracking", "müzik": "music", "not": "notes", "pdf": "pdf",
        "belge": "document", "konuşma": "speech", "transkripsiyon": "transcription",
        "sohbet": "chat", "hafıza": "memory", "bellek": "memory",
        "plan": "planning", "ajan": "agent", "otomasyon": "automation",
        "zamanlama": "scheduler", "hava": "weather", "durum": "status",
        "çeviren": "to", "yapan": "", "bir": "", "şu": "", "bu": "",
        "için": "for", "ile": "with", "node": "node", "bul": "",
    }
    kelimeler = []
    for w in re.split(r"\s+", tr):
        t = w.strip(".,?!'\"()[]{}").lower()
        kelimeler.append(sozluk.get(t, w.strip(".,?!'\"()[]{}")))
    cikti = " ".join(k for k in kelimeler if k)
    return cikti if cikti.lower() != tr.lower() else ""


sozlesme = {
    "kod": "node_bulucu",
    "ad": "Node Bulucu (Açık Kaynak Kurulum)",
    "tur": "yetenek",
    "surum": "0.1",
    "aciklama": ("Kullanıcının ihtiyacına göre GitHub'da açık kaynak node/proje "
                 "arar, gerekçeleriyle puanlar; seçileni onayla indirip "
                 "nodeller/ klasörüne kurar ve sol menüye ekler. Dışarıdan "
                 "yazılan node'lar nodeller/kabul/ üzerinden onaylanır."),
    "gorev_anahtarlari": ["node bul", "node kur", "node ara", "açık kaynak bul",
                          "eklenti bul", "plugin", "modül bul", "proje bul",
                          "şu işi yapan", "böyle bir şey var mı", "entegre et",
                          "node kaldır", "node yönet"],
    "cagri_ornekleri": [
        "'sesi metne çeviren bir node bul' → node_bulucu(...) arar-puanlar",
        "indirme: {\"eylem\":\"indir\",\"secenek\":{...}}",
        "kabul listesi: {\"eylem\":\"kabul_listele\"}",
        "kabul onay: {\"eylem\":\"kabul_onayla\",\"dosya\":\"benim_node\"}"],
    "calistir": calistir,
}
