# ARAMA KURULU — Tasarım Belgesi (v1)
Tarih: 2026-10-13 | Durum: ONAY BEKLİYOR (kod yazılmadı)
Kaynak: Kullanıcının ChatGPT ile geliştirdiği "uzman birim + orkestratör" vizyonu,
mevcut sistem mimarisiyle (beden metaforu, EL onay kapısı, tak-sök modüller) birleştirildi.

---

## 1. TEMEL KARAR: Kurul bir ORGANDIR, üyeleri YETENEKTİR

ChatGPT'nin önerdiği yapı bizim iki katmanlı modül sistemimize birebir oturur:

```
KULLANICI SORUSU
      │
      ▼
KARAR MERKEZİ (zaten var) ──► "bu bir ARAŞTIRMA işi" der
      │
      ▼
ARAMA KURULU (organ — sürekli aktif, sol menüde takılı görünür)
   görev çözümleyici · uzman seçici · toplayıcı · puanlayıcı · raporlayıcı
      │
      ├──► UZMAN YETENEKLER (tak-çıkar, gerektiğinde çağrılır)
      │     ├ web_arastirmacisi   (ddgs tabanlı — mevcut "arama"nın yerine geçer)
      │     ├ kod_arastirmacisi   (GitHub API — anahtarsız çalışır)
      │     ├ akademik_arastirma  (OpenAlex + arXiv — anahtarsız, ücretsiz)
      │     ├ kisi_arastirmacisi  (Maigret/Sherlock mantığı — İZİN GEREKTİRİR)
      │     ├ fiyat_karsilastirma (SearXNG/mağaza adaptörleri — SONRAYA BIRAKILIR)
      │     └ guncel_veri         (hava: open-meteo, döviz: TCMB — anahtarsız)
      │
      └──► her uzman sökülebilir → Kurul kalan uzmanlarla çalışmaya devam eder
           (boş üye listesi = Kurul sadece web_arastirmacisi'ne düşer, çökmez)
```

Neden bu ayrım önemli:
- Kurul beyin-üstü bir "koordinasyon organı"dır; kapatınca sistemde arama hiç olmaz.
- Uzmanlar ellerdir; tek tek söküp takılır. Yeni uzman = yeni klasör, çekirdeğe dokunmaz.
- Karar merkezi artık sadece "hafif/ağır model" değil, "hangi uzman(lar)" bilgisini de üretir.

## 2. KURULUN İÇ AKIŞI (5 aşama)

1. **GÖREV ANALİZİ** (ağır model, yapılandırılmış JSON çıktı):
   `kategori` (genel/kod/akademik/kişi/fiyat/sayısal-veri/düşünsel), `net_istediklerim`,
   `alt_sorgular[]`, `bolum_gerektiginde_secilecek_uzmanlar[]`, `derinlik` (hızlı|kurul).
2. **UZMAN SEÇİMİ**: Analiz sonucuna göre 1-3 uzman paralel göreve çağrılır.
   Karmaşık sorularda birden fazla uzman aynı anda (ChatGPT'nin doğru gözlemi).
3. **VERİ TOPLAMA**: Her uzman ortak sözleşmeyle döner (bkz. §4). Ham sonuç + kaynak + zaman damgası.
4. **DOĞRULAMA & PUANLAMA** (ağır model): Çapraz kontrol (en az 2 bağımsız kaynak),
   güncellik denetimi, kategoriye göre ÖZGÜN ağırlık seti (§3), belirsizlik etiketleme.
5. **RAPOR**: Gerekçeli cevap + kaynak listesi + güven/belirsizlik notları.
   Tam rapor El ile `veri/arastirma_raporlari/` klasörüne dosya olarak yazılır
   (onay akışı devreye girer), sohbete özet + dosya yolu düşer. Hafıza organı özeti öğrenir.

## 3. PUANLAMA: TEK FORMÜL YOK, KATEGORİYE ÖZGÜN AĞIRLIKLAR

ChatGPT'nin uyarısı yerinde: ürün 90/100 almak "en iyi" demek değil, "ölçütlere güçlü eşleşme" demek.
Başlangıç ağırlıkları (kullanıcı Ayarlar→Arama Kurulu'ndan değiştirebilir):

| Kategori        | Uygunluk | Güvenilirlik | Güncellik | Kanıt/Detay | Popülerlik/Bor. | Fiyat/Perf. |
|-----------------|----------|--------------|-----------|-------------|------------------|--------------|
| Ürün/fiyat      | %35      | %20          | %15       | %10         | %10              | %10          |
| Kod/open-source | %30      | %25 (lisans+bakım) | %15 | %15 (doküman) | %15 (yıldız/kullanım) | — |
| Akademik        | %25      | %30 (yöntem+dergi) | %10 | %25 (bulgu netliği) | %10 (atıf) | — |
| Kişi/hesap      | %40 (eşleşme güveni!) | %20 | %15 | %25 | — | — |
| Sayısal veri    | —        | %50 (resmî kaynak) | %50 (zaman damgası) | — | — | — |

Her raporda zorunlu alanlar (ChatGPT'nin 5 maddesi aynen alınır):
**Kaynak güveni · Güncellenme zamanı · Eşleşme güveni · Belirsizlikler · Gerekçe.**

## 4. UZMAN SÖZLEŞMESİ (ortak giriş/çıkış şeması)

Her uzman yeteneği şu sözlüğü döner — Kurul hiçbir uzmanın iç yapısını bilmez:

```python
{
  "uzman": "kod_arastirmacisi",
  "sorgu": "yerel hafıza modülü python",
  "sonuclar": [
    {"baslik": ..., "ozet": ..., "url": ..., "kaynak_tipi": "github",
     "guncellik": "repo push 2026-08-26", "ek_veri": {"yildiz": 3017, "lisans": "MIT"}}
  ],
  "durum": "ok" | " kisitli" | "hata",
  "not": "bot korumasına takıldıysa buraya yazar"
}
```

## 5. CHATGPT PLANINDAN ALDIKLARIMIZ / REDDETTİKLERİMİZ

| ChatGPT önerisi | Bizim kararımız | Neden |
|---|---|---|
| SearXNG genel web | **REDDERK → ddgs** | SearXNG ayrı sunucu/docker ister; "tek bat" hedefimize aykırı (araştırma günlüğü ADIM 2'de kanıtlandı) |
| Crawl4AI sayfa okuma | **ALTERNATİFLİ** | Önce ddgs'nin kendi `content` çekicisi; yetmezse Crawl4AI ayrıca değerlendirilir (ağır bağımlılık riski) |
| Maigret+Sherlock kişi arama | **KAVRAMI AL, MOTORU AYRI KARAR** | Bağımlılık zinciri ağır; önce "kimlik avı bölgesi" kuralları konur, motor sonra oylanır |
| OpenAlex+arXiv+Crossref+SemanticScholar | **KISMEN AL → OpenAlex + arXiv** | İkisi de tamamen anahtarsız/ücretsiz; Crossref ve S2 sınırlı/anahtar gerektirebiliyor — rafada tutulur |
| SearchClaw derin araştırma deseni | **YÖNTEMİ AL, KODU ALMA** | Planla→ara→okuyu-not çıkar→raporla döngüsünü kendi ağır modelimizle taklit ederiz (mevcut günlüğümüzdeki karar) |
| Ürün/mğaza adaptörleri | **SONRAYA** | Site yapıları sık değişir; bakımı ayrı proje. İlk sürümde yok |
| Dinî/felsefi uzman | **KATEGORİ OLARAK VAR, UZMAN YOK** | İlk sürümde akademik+web uzmanlarının kombinasyonuyla karşılanır |
| Hava/döviz bağlayıcıları | **AL → open-meteo + TCMB** | Anahtarsız, resmî, Türkçe uyumlu (TCMB günlük kur XML/JSON) |
| Puanlama kanıtın yerine geçmesin | **BİREBİR ALINDI** | §3'teki zorunlu 5 alan |

## 6. GÜVENLİK VE İZİN (EL kapısıyla entegre)

- **Dışarı çıkış = onaylı eylem.** Kurulun ilk internet isteğinde panelde onay kartı çıkar:
  ✔ Bu sefer · 🔓 Bu oturum boyunca · ♾ Kalıcı (Ayarlar→Arama Kurulu'ndan iptal) · ✖ Reddet.
- **Kişi araştırması özel bölge:** ad/soyad/kullanıcı adı sorguları otomatik olarak
  "yüksek hassasiyet" etiketi alır → her oturumda en az bir kez sorulur (kalıcı izin olsa bile hatırlatma satırı).
  Kimlik eşleşmesi asla kesin kabul edilmez; eşleşme güveni %100 altında gösterilir.
- Hiçbir uzman login/çerez/özel veri kullanmaz; yalnızca herkese açık uç noktalar.
- Tüm aratımlar `veri/gunlukler/arastirma_gunlugu.jsonl`'a yazılır (El günlüğüyle aynı desen).

## 7. SOL MENÜ VE PANEL (tak-sök arayüzü)

- Sol panelde **"ARAMA KURULU"** organ satırı: açık/kalıp anahtarı + kaç uzman bağlı rozeti (örn. 4/6).
- Kurula tıklayınca açılan alt liste: her uzman için takili/gömülü durumu, **Sök** ve **Depodan Yenile** butonları.
- Ayarlar→Arama Kurulu: derinlik tercihi (hızlı tek uzman / kurul çoklu), ağırlık tabloları,
  dışarı çıkış izni derecesi, rapor klasörü yolu.
- Sohbet baloncuğunda kurul çalışırken adım düğmeleri: `[analiz] → [web+kod uzmanları çağrıldı] →
  [7 kaynak doğrulandı] → [rapor hazır]` (tıklanınca ara çıktılar görülür — şeffaflık).

## 8. DOSYA YAPISI (öneri)

```
organlar/arama_kurulu/
   modul.py          → organ sözleşmesi: baslat()/dur()/sonne()
   gorev_analiz.py   → 1. aşama (ağır model JSON şeması)
   toplayici.py      → uzman çağırma, eşzamanlı toplama, timeout
   puanlayici.py     → §3 ağırlık tabloları + 5 zorunlu alan
   raporcu.py       → nihai metin + El'e dosya yazdırma
yetenekler/
   web_arastirmacisi/  (ddgs; mevcut "arama" modülünün üstü)
   kod_arastirmacisi/  (GitHub API anahtarsız)
   akademik_arastirma/ (OpenAlex + arXiv)
   guncel_veri/        (open-meteo + TCMB)
   kisi_arastirmacisi/ (motor sonra; ilk sürümde boş iskelet)
```

## 9. FAZLAR (önerilen sıralama)

- **FAZ 1 (ilk kod):** Kurul organı + web_arastirmacisi (ddgs) + kod_arastirmacisi + guncel_veri.
  Onay kapısı + sol menü tak-sök + rapor dosyası. → En yüksek fayda / en az bağımlılık.
- **FAZ 2:** akademik_arastirma + puanlama ağırlıklarının arayüzden düzenlenmesi + çoklu uzman paralelliği.
- **FAZ 3:** kisi_arastirmacisi (motor oylamasıyla) + fiyat karşılaştırma adaptörleri.
- **FAZ 4:** "Modül Avcısı" — bu belgedeki araştırma metodunu (ADIM 0→4) otomatikleştirip
  depodan yeni uzman bulup kullanıcıya öneren meta-yetenek.

## 10. ONAY SORULARI

1. Faz-1 kapsamı (Kurul + web/ddgs + GitHub + hava/döviz) onaylanıyor mu?
2. Mevcut `yetenekler/arama` modülü `web_arastirmacisi` olarak yükseltilecek mi (eski silinip depoya alınacak mı)?
3. Kişi aramada "her oturumda en az bir hatırlatma" kuralı kabul mü?
4. Raporların El ile diske yazılması (klasör: `veri/arastirma_raporlari/`) uygun mu?
