# YÖNERGE — DIŞARIDA SİSTEM/NODE ÜRETİMİ VE KABUL KLASÖRÜ ENTEGRASYONU

> **Bu dosyanın amacı:** Başka bir sohbette (ChatGPT/Claude/yerel LLM) yeni bir
> sistem/node tasarlatıp `MLAO/nodeller/kabul/` klasörüne attığında, onun
> **ilk denemede** sisteme takılabilmesi için gerekli tüm teknik sözleşmeyi
> tek yerde toplar. Dışarıdaki sohbet penceresine bu dosyayı olduğu gibi
> ver; "bana bu sözleşmeye uyan bir node paketini yaz" de.

Sistem adı: **MLAO** (Modüler Yerel Zekâ). Kök dizin: proje ana klasörü.
Hedef platform: Windows + Python 3.10+, bağımlılık = yalnızca `requests`
(Flask sunucu zaten kurulu; node ek bağımlılık getirirse nedenini belirt).
Tüm sözlük anahtarları ve kod tanımlayıcıları **Türkçe**.

---

## 1. PAKET ANATOMİSİ (zorunlu yapı)

Node, TEK bir klasördür ve şu iki dosyayı İÇERMEK ZORUNDADIR:

```
nodeller/kabul/<kod_adi>/
├── modul.py            ← asıl kod (aşağıdaki şablona birebir uy)
└── modul_bilgisi.py    ← yalnızca metadata sözlüğü
```

Ek dosyalar serbest: `kurulus.py` (modül içi ayar), `birimler/*.py`,
`README.md`. Klasör adı (`kod_adi`) küçük harf, alt çizgi, Türkçe karaktersiz.

### 1.1 `modul_bilgisi.py` şablonu

```python
# -*- coding: utf-8 -*-
MODUL_BILGISI = {
    "kod": "sayac_tutucu",          # klasör adı ile AYNI olmalı
    "ad": "Sayfa Sayaç Tutucu",      # panelde görünen ad
    "tur": "node",                   # sabit: "node"
    "surum": "1.0",
    "aciklama": "Hangi sayfada ne kadar kaldığını yerel sayar.",
}
```

### 1.2 `modul.py` şablonu (asgari imza)

```python
# -*- coding: utf-8 -*-
"""NODE ADI — tek paragraflık iş tanımı."""
from __future__ import annotations
from typing import Dict

def calistir(metin: str, **saglama) -> dict:
    """ZORUNLU GİRİŞ NOKTASI.
    metin   : kullanıcı isteğinin ham metni VEYA JSON sözlüğe çevrilebilir metin
    saglama : oturum, model_adı gibi ek anahtarlar gelebilir — .get() ile oku
    DÖNÜŞ  : mutlaka dict:
             {"basarili": True,  "yanit": "insan-okur metin", "ozet": "tek satır"}
             {"basarili": False, "hata": "neden başarısız", "yanit": ""}
    """
    return {"basarili": True, "yanit": f"Denenen: {metin}", "ozet": "test"}

sozlesme = {                       # ZORUNLU — panel bu sözlükle listeler
    "kod": "sayac_tutucu",         # modul_bilgisi ile birebir aynı
    "ad": "Sayfa Sayaç Tutucu",
    "tur": "node",                 # organ/yetenek DEĞİL → "node"
    "surum": "1.0",
    "aciklama": "...",             # tek cümle
    "gorev_anahtarlari": ["sayfa", "sayaç"],   # karar merkezi eşleştirme ipuçları
    "cagri_ornekleri": ["'kaç kez baktım' → sayac_tutucu(...)"],
    "calistir": calistir,          # fonksiyon referansı (string değil!)
}
```

### 1.3 Kabul hattında çalışan doğrulama (kodda görebilirsin)

`web/uygulama.py → api_node_onayla()` şunları sırayla kontrol eder; BİRİ
bile takılırsa node reddedilir ve kabul'de kalır:

1. Onay kartı (kapıcı `alan="node"`) — kullanıcı "kabul et" demeden taşınmaz.
2. `modul.py` var mı?
3. Dosya **import edilince exception veriyor mu?** (syntax hatası = ret)
4. `sozlesme` özelliği var mı ve `calistir` **callable** mı?
5. Taşıma: `nodeller/kabul/<ad>` → `nodeller/<kod>` (+ çakışmada `_HHMMSS`).

Dolayısıyla dışarıda yazdıracağın koda sormanın en ucuz garantisi:
*"Python 3.10'da `python -c 'import modul'` hatasız geçmeli ve
`modul.sozlesme['calistir']('test')` patlamamalı."*

---

## 2. ÇEKİRDEK API — NODE'UN ELİNDEKİ GÜÇLER

Node çekirdeğe **lazy import** ile erişir (modül yüklenirken değil,
`calistir` içinde `try/except` ile). Örnek zincir:

```python
def _cekirdek():
    try:
        from cekirdek import yapilandirma
        from cekirdek.modul_iskeleti import TEKIL
        from cekirdek.onay import TEKIL_KAPICI
        return yapilandirma, TEKIL, TEKIL_KAPICI
    except Exception:
        return None, None, None
```

| Yetenek | Çağrı | Not |
|---|---|---|
| Ayar oku/yaz | `yapilandirma.yukle()` / `.guncelle({...})` | atomik, thread-güvenli |
| Model üretimi | `ollama_kontrol.OllamaIstemcisi(adres).uretim(model, mesajlar, sistem=..., gorseller=[base64])` | gorseller → çok-modal |
| Görsel model adı | `yukle()["modeller"].get("goruntu_modeli")` | boşsa adında vision/llava geçen yüklü modele düşer |
| Hafıza yaz/oku | hafıza organı → `.kaydet(oturum, rol, içerik)`, `.ara(sorgu, oturum)` | tercih öğrenme buradan |
| Onay iste | `TEKIL_KAPICI.denetle(eylem, hedef, aciklama, alan="<senin alan>")` | `{"onayli": bool}` döner; onaysız İŞ YAPMA |
| Arama kurulu | `TEKIL.modulu_calistir("arastirmaci", json.dumps({"eylem":"kurul_ara","sorgu":...}))` | kanıt dosyası alır |
| Diğer node'lar | `TEKIL.modulu_calistir(kod, girdi)` | tak-sök dostu kompozisyon |

**YASAKLAR:** `os.system`, `subprocess` ile ağa/diska izinsiz yazma, veri
sızıntısı, kapıcıyı atlayıp sessiz izin notu bırakma. Gerekiyorsa ACIKÇA
belgelendir — kabul onay kartında kullanıcı uyarılır.

---

## 3. ARAYÜZ GEREKTİREN SİSTEMLER (asıl sorunun cevabı)

Panel Flask/Jinja tabanlı, SPA framework YOK. Node arayüzü üç katmanda
entegre olur; hepsi mevcut altyapıyla çalışır, çekirdeğe dokunmaz:

### Katman A — Sohbet chip'i (sıfır maliyet, her nodda otomatik)
Karar merkezi node'u çağırdığında yanıt sohbete düşer; sol menüde anahtar
kelimeyle görünür. Karmaşık UI gerekmiyorsa DUR — A yeter.

### Katman B — Panel widget'ı (önerilen standart yol)
Node `sozlesme`ye arayüz bildirimi ekler:

```python
"panel_widget": {
    "konum": "aside_alt",              # ya da "ust_menu"
    "html_id": "w-sayac",
    "api": "/api/modul_cagir",          # mevcut uç — POST {kod, girdi}
    "periyot_sn": 30,                   # yoksa buton-dokunuşlu tek çekim
},
```

Widget HTML'i node'un kendi `panel_bolumu()` fonksiyonu üretir:

```python
def panel_bolumu() -> str:
    """Güvenli HTML: <script> İÇERMEZ; davranış için data-* + mevcut panel.js."""
    return ('<div id="w-sayac" class="bolum" data-node="sayac_tutucu">'
            '<h3>Sayaç</h3><span class="not">veri bekleniyor…</span></div>')
```

Kural: **HTML içinde `<script>`/`onclick` YASAK** (XSS yüzeyi küçültür).
Etkileşim, `data-node` üzerinden panel.js'in genel devre-yakalayıcısı ile
`/api/modul_cagir`'e POST atarak yapılır. Bu uç BEKLEYEN ONAY KARTLARINI da
döndürür (`onay_kartlari` alanı) → widget bunu panel.js'in mevcut onay-kart
motoruna besler, yeni JS yazmaya gerek yok. CSS için mevcut sınıfları kullan
(`.bolum`, `.model-kart`, `.btn`, `.chip`).

### Katman C — Tam sayfa / canlı arayüz gerektiren ağır sistemler
(ör. sürükle-bırak pano, canlı grafik) → panelde YENİ sekme açmak yerine
node kendi **Flask blueprint'ini** önerir:

```python
# modul.py içinde
def flask_blueprint():
    from flask import Blueprint, jsonify
    bp = Blueprint("sayac_tutucu", __name__, url_prefix="/node/sayac_tutucu")
    @bp.route("/durum")
    def durum(): return jsonify(hazir=True)
    return bp
```

Onay hattında `flask_blueprint` callable ise `app.register_blueprint(bp)`
çağrılır (tek satır hook; node sökülünce route'lar da ölür). React/Vue gibi
build-adımlı frameworkler KASITLI olarak dışarıda — node statik HTML +
vanilla-JS ile kendi klasöründen servis eder.

### Karar ağacı (dışarıdaki sohbete bunu söylet)
```
UI gerekiyor mu?
├─ Hayır / sadece metin çıktı        → Katman A
├─ Buton + kısa veri gösterimi       → Katman B (widget)
└─ Çok adımlı form / canlı grafik    → Katman C (blueprint)
Her durumda: çekirdek dosyalara dokunma, tek klasör kal.
```

---

## 4. DIŞARIDA YAZDIRMA PROSEDÜRÜ (kullanıcı adımları)

1. Bu MD'yi yeni sohbet penceresine yapıştır + görev tarifini ekle:
   *"Bu sözleşmeye uyan `<kod>` node'unu yaz. Tek klasör: modul.py +
   modul_bilgisi.py. Bağımlılık: stdlib + requests. Katman A/B/C seçimini
   gerekçelendir."*
2. Gelen kodu **temiz odada** test et (sisteme sokmadan önce):
   ```bash
   mkdir -p test && cd test
   # gelen iki dosyayı buraya koy
   python -c "import modul; print(modul.sozlesme['kod']); \
              print(modul.sozlesme['calistir']('deneme'))"
   ```
   Hatasız + dict dönüyorsa hazır.
3. `nodeller/kabul/<kod>/` altına yerleştir (klasör adı = `kod`).
4. Panel → Ayarlar → **Node Yönetimi** → kabul listesinde "Onayla" → onay
   kartı → "Yalnız bu sefer". Node `nodeller/`e taşınır, sol menüde belirir.
5. Sohbette dene: `/sayac_tutucu girdi ...` veya doğal dil (anahtar
   kelimeler karar merkezine yön verir).
6. Beğenmezsen 🗑 sök → klasör otomatik `nodeller/kabul/`e geri döner,
   oradan tekrar "Geri Kur" edebilirsin. (Silme yok, hep geri alınabilir.)

**Performans değerlendirmesi için not ver:** yanıt gecikmesi, bellek,
beklenmedik hata, onay kartı davranışı, hafıza etkileşimi (1-5).

---

## 5. TEST SENARYOSU HAVUZU (hazır sipariş cümleleri)

| # | Sipariş | Zorladığı şey | Beklenen katman |
|---|---|---|---|
| T1 | "Son 7 günün nöbetçi göz raporlarından en çok kullanılan 3 pencereyi özetleyen `goz_analiz` node'u" | hafıza okuma, JSON parse | A |
| T2 | "Seçili metni Türkçe açıklayan `pano_cevirici` (clipboard'suz: textarea kutusu)" | onay kartı, goruntu_modeli fallback, widget | B |
| T3 | "Kur/hava üst-bar widget'ına alternatif tema renkleri ayarlayan `tema_secici`" | `yapilandirma.guncelle`, canlı önizleme | B |
| T4 | "Konuşma geçmişinden haftalık alışkanlık grafiği çizen `aliskanlik_grafigi` (SVG üretir)" | hafıza + grafik | C |
| T5 | Kasıtlı bozuk paket: eksik `sozlesme` / syntax hatası / `calistir` yok | RED akışı: kabul'de kalır, neden gösterilir | — |

T5'i de mutlaka dene — sistemin savunma hattı ancak böyle ölçülür.

---

## 6. MİMARİ SINIRLAR (node asla bunlara dönüşmez)

- Node **organ olamaz** (sürekli döngü/arka plan thread ancak ekran_gozu
  gibi meşru nöbetçi örneklerinde, `threading.Event` + durdurma bayrağıyla).
- Node, karar merkezi/gönderici/panel dosyalarını DÜZENLEMEZ; entegrasyon
  yalnızca kendi klasörü + sozlesme anahtarları + (C katmanıysa) blueprint.
- Yeni pip bağımlılığı: `gereksinimler.txt`'e eklemeyi ÖNER, kendin kurma;
  kurulum kullanıcı onayına bırakılır.
- Veri yazacaksan yalnız `veri/` ağacı (node'a özel alt klasör önerilir:
  `veri/<kod>/`).

---

*Belge sürümü: 1.0 — 2026-10-14. Kod referansları: `web/uygulama.py`
(api_node_onayla, _kabul_eslesmeleri, api_modul_sok/geri_kur),
`cekirdek/modul_iskeleti.py` (TUR_NODE, arşiv alt-klasör filtresi),
`nodeller/meu/modul.py` (minimal örnek paket).*
