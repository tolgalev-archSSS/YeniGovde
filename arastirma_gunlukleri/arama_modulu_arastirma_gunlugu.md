# ARAŞTIRMA GÜNLÜĞÜ — "Araştırmacı" (İnternet Arama) Yeteneği
Tarih: 2026-10-13 | Amaç: Sisteme tak-çıkar edilebilir internet arama yeteneği için en iyi açık kaynak adayı bulmak.
Bu günlük, ileride sisteme eklenecek "Modül Avcısı" yeteneğinin davranış taslağıdır: her adım, sorulan soru ve değerlendirme mantığı kayıt altındadır.

---

## ADIM 0 — Görevi Anlama ve Kriter Çıkarma
**Kendime sorduğum soru:** Kullanıcı tam olarak ne istiyor?
**Cevap:** Arama tek düze değil; alt aşamalara bölünebilmeli: (a) kişi/şirket arama, (b) konu arama, (c) karşılaştırmalı arama. Ayrıca sayfa içeriğini okuyup DEĞERLENDİREBİLMELİ (sadece link listesi yetmez). İnternet kısıtı yok, API anahtarı istemiyorum (tamamen lokal/ücretsiz), Türkçe uyumlu olmalı, EL modülündeki gibi izin katmanına bağlanabilmeli.
**Çıkarılan kriterler:**
- K1: Anahtarsız ücretsiz arama (API kaydı gerektirmesin)
- K2: Sayfa içerik çekme (fetch/read) desteği
- K3: Python kütüphanesi olsun (çekirdeğe fonksiyon olarak sarılabilir)
- K4: Hafif bağımlılık (sistem şişmesin)
- K5: Bakımı aktif (2026'da canlı geliştirme)
- K6: Lisans serbest (MIT/Apache tercih; ticari değil ama baş ağrısı istemiyoruz)
- K7: Modül iskeletine uygun (tak-sök, soenne() temizliği)
- K8: Karşılaştırmalı/çoklu sorgu desenine uygunluk (aynı motorda birden çok aratım)
- K9: Bot korumasına dayanıklılık (engellenmeden "her yere girebilme" isteği)

## ADIM 1 — Envanter Taraması (Geniş Aday Havuzu)
**Soru:** Bu işi yapan neler var, kategoriler nasıl ayrışıyor?
**Yöntem:** GitHub arama API'si ile 5 farklı sorgu (web search agent / search api self-hosted / duckduckgo library / perplexity alternative / deep research), yıldız sıralı.
**Bulgu — 4 doğal kategori ortaya çıktı:**
1. TAM TARAYICI/ASistan uygulamaları (LibreChat, Khoj, BrowserOS, Open Interpreter) → bizim sistemle "beyin" çatışması yaşar, elenir.
2. DERİN ARAŞTIRMA ÇERÇEVELERİ (gpt-researcher, MindSearch, deep-research, dzhng) → doğru fikir ama kendi LLM'lerine bağımlılar; Ollama köprüsü ek yük.
3. META-ARAMA MOTORU SUNUCULARI (SearXNG, websurfx, openserp) → güçlü ama ayrı servis/docker/Redis ister; "tek bat ile açılır" hedefimize aykırı.
4. ARAMA KÜTÜPHANELERİ (ddgs, serperlib, tavily-client...) → doğrudan Python'a gömülebilir. **En uygun kategori.**

## ADIM 2 — Kategori İçi Kısa Liste + Doğrulama
**Soru:** Kategori 4'te gerçekten yaşayan projeler hangileri? (GitHub API yanıltıcı olabilir, çatal depolara dikkat!)
**Yöntem:** pypi.org JSON API + repo bazlı doğrulama + kullanıcı bazlı tarama (user:deedy5).
**Doğrulama sonuçları (canlı veri):**
- `deedy5/ddgs` → 3.017★, son push 2026-08-26, **MIT**, PyPI sürüm 9.16.0 "Dux Distributed Global Search" — DuckDuckGo'nun kapanmış `duckduckgo_search` paketinin resmî devamı. Çok motorlu metasearch: text/news/images/videos + `content` (sayfa içeriği indirme) desteği.
- `searxng/searxng` → 38.328★, son push bugün, AGPL-3.0 → sunucu kurulumu + docker gerektirir, lisans viral.
- `assafelovic/gpt-researcher` → 30.067★, Apache-2.0, Python → ama FastAPI+Node+broker zinciri, ~50+ bağımlılık.
- `InternLM/MindSearch` → 6.943★, JavaScript/Next.js → mimari uyumsuz.
- `dzhng/deep-research` → 19.781★, TypeScript → mimari uyumsuz.
- `neon-mmd/websurfx` → 1.216★, Rust sunucu → entegrasyon köprüsü gerekir.

## ADIM 3 — Puanlama (K1–K9 üzerinden 0–10)
| Kriter | ddgs | SearXNG | gpt-researcher | MindSearch | deep-research (TS) |
|---|---|---|---|---|---|
| K1 Anahtarsız arama | 10 | 9 | 7 (Tavily önerir) | 6 | 6 |
| K2 İçerik çekme | 9 (`content`) | 7 | 9 | 6 | 7 |
| K3 Python kütüphanesi | 10 | 5 (sunucu) | 6 (servis) | 1 | 0 |
| K4 Hafiflik | 10 (~5 paket) | 3 | 2 | 2 | 3 |
| K5 Canlı bakım | 8 | 10 | 9 | 6 | 4 |
| K6 Lisans | 10 MIT | 5 AGPL | 9 Apache | 9 Apache | 10 MIT |
| K7 Tak-çıkar uyumu | 10 | 4 | 3 | 2 | 2 |
| K8 Çoklu/karşılaştırma sorgusu | 9 (hızlı paralel) | 7 | 10 (planlayıcı) | 8 | 8 |
| K9 Bot dayanıklılığı | 8 (primp tarayıcı taklidi) | 8 | 7 | 6 | 6 |
| **ORTALAMA** | **9.4** | **6.7** | **6.3** | **4.7** | **4.9** |

## ADIM 4 — "En İyi"ye Nasıl Kanaat Getirdim?
1. **Tek başına yıldız sayısı yetmez** (SearXNG 38k★ ama K3/K4/K6/K7'de eleniyor) → kriter ağırlıklı puanlama yaptım.
2. **Canlı veriyle doğruladım**: PyPI güncelliği + repo push tarihi + lisans alanını API'den teker teker çektim; varsayım değil kanıt kullandım.
3. **Mimari süzgeci**: Bizim sistemde beyin zaten Ollama'da. Adayın yapacağı tek şey "göz+kulak" olmalı (arama+okuma), düşünme değil. Bu yüzden kendi LLM döngüsü olan her şey (kategori 1-2) yapısal olarak elendi — puanı yüksek olsa bile.
4. **Karar:** **ddgs birinci aday**; gpt-researcher'ın "önce planla→ara→okuyup not çıkar→raporla" deseni ise DERİN ARAŞTIRMA moduna kendi çekirdeğimizle (ağır model + El'in dosya yazma yetisi) taklit edilerek alınacak. Yani: motor = ddgs, yöntem = gpt-researcher fikri, beyin = bizim ağır modelimiz.

## ADIM 5 — Entegrasyon Taslağı (Onay Bekliyor)
```
yetenekler/arastirmaci/
  modul.py      → sözleşme: çağril()/soenne(); alt-eylemler:
                  kisi_ara(sorgu)   → dar filtre, profil/haber odaklı
                  konu_ara(sorgu)   → standart web+news araması
                  karsilastir(liste)→ her öğe için ayrı arama + içerik okuma, yan yana tablo
                  derin_ara(konu)   → planla→ara→okuyu-not-cikar→özetle (çok tur, ağır model)
                  sayfa_oku(url)    → içerik çekme + HTML→temiz metin
  gunluk.py     → her aratım loglanır (El'deki gibi)
```
- İzin: dışarı çıkış = hassas eylem → panel onay kartı ("bu oturum boyunca" seçeneğiyle, EL tasarımıyla birebir aynı kapıcı).
- Bağımlılık: `ddgs` (PyPI) → gereksinimler.txt'e eklenir; sökülünce kaldırılır iz bırakmaz.
- Değerlendirme: ham sonuçlar ağır modele gider; model "hangi kaynak güvenilir, özet şu" diye raporlar; hafıza organı sonucu öğrenir.

## SONUÇ VE ÖNERİ
**Öneri: ddgs (MIT, PyPI 9.x) üzerine yerli "Araştırmacı" yeteneği.** Alternatifler ya ağır servis (SearXNG) ya yabancı beyin taşıyor (gpt-researcher/MindSearch). Kullanıcı onay verirse bu yetenek kodlanır; "Modül Avcısı" gelecekte tam bu günlüğün metodunu (Adım 0→4) otomatik tekrarlayacak.
