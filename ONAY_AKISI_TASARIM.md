# EL MODÜLÜ — ONAY AKIŞI TASARIMI (v1 · kod öncesi)

Bu belge, `yetenekler/el/` modülünün panel ile kuracağı izin/onay akışını
tanımlar. Onaylar **sohbet baloncuğu** içinde yaşar; ayrı bir sekme/pencere
yoktur. Kullanıcı onay vermezse eylem 5 dakika sonra kendiliğinden düşer.

---

## 1. Katılımcılar ve rolleri

| Bileşen | Dosya | Görevi |
|---|---|---|
| El motoru | `yetenekler/el/modul.py` | İsteği çözümler, kapıcıya sorar, gerekirse onay kartı üretir, eylemi uygular, günlüğe yazar |
| Kapıcı | `yetenekler/el/kapici.py` | Kırmızı çizgiler + yetkili bölge + izin defteri kontrolü |
| İzin defteri | `ayarlar/onay_defteri.json` | Oturum boyu / kalıcı izin kayıtları |
| Bekleyen kuyruğu | bellekte (thread-safe sözlük) | `kimlik → {eylem, durum}` |
| Panel API | `web/uygulama.py` | `/api/onaylar`, `/api/onay_ver` uçları |
| Sohbet döngüsü | `cekirdek/gonderci.py` | Yanıtın içine `onay` kartını gömer, mesajı geçici işaretle kaydeder |
| Arayüz | `web/panel.html` | Kartı çizer, butonları API'ye bağlar, sonucu baloncuk olarak ekler |

## 2. Karar ağacı (her eylem isteğinde)

```
İstek gelir (ör: "C:\Notlar\x.txt dosyasını sil")
   │
   ├─ KIRMIZI ÇİZGİ mi?          → HAYIR: "Sistem kritik bölge, El oraya uzanamaz."
   │  (C:\Windows, Program Files, disk kökü, sistem sürücüleri,
   │   bu projenin kendi çekirdek/web klasörleri)
   │
   ├─ YETKİLİ BÖLGE DIŞI mı?     → HAYIR: "El yalnızca yetkili bölgelerde çalışır.
   │  (varsayılan: tüm ev dizini +                     Ayarlar→El'den bölge ekleyebilirsin.)"
   │   Ayarlar→El_bölgeleri ile büyütülebilir)
   │
   ├─ OKUMA eylemi mi?            → SERBEST: doğrudan yapılır (oku/listele/ara/bilgi).
   │
   ├─ ZATEN İZİN VAR MI?          → EVET: doğrudan yapılır.
   │   • kalıcı kayıt eşleşirse        (izin defterinden)
   │   • oturum kaydı eşleşirse        (oturum bitince silinir)
   │
   └─ HAYIR → ONAY KARTI ÜRET → sohbet baloncuğunda göster → bekle
```

## 3. Onay kartı (sohbette görünen nesne)

Model yanıtının yanında JSON olarak taşınır; panel bunu güzel kutuya çevirir:

```json
{
  "kimlik": "onay_a1b2c3",
  "durum": "bekliyor",              // bekliyor | onaylandi | reddedildi | suresi_doldi
  "eylem_ozet": "Dosya silme (çöp kutusuna): C:\\Users\\ben\\Notlar\\x.txt",
  "detaylar": ["hedef: ...", "boyut: 12 KB", "yedek: veri/yedekler/..."],
  "secenekler": [
    {"kod": "evet",       "etiket": "✔ Yalnız bu sefer"},
    {"kod": "oturum",     "etiket": "🔓 Bu oturum boyunca (silme)"},
    {"kod": "kalici",     "etiket": "♾ Kalıcı izin (bu tür + bu bölge)"},
    {"kod": "hayir",      "etiket": "✖ Reddet"}
  ]
}
```

### İzin dereceleri ve eşleştirme anahtarı
| Derece | Anahtar örneği | Ömür |
|---|---|---|
| tek seferlik | (kayıt tutulmaz) | sadece bu eylem |
| oturum boyu | `"el:sil:C:\Users\ben"` | tarayıcı oturumu (`oid`) bitince silinir |
| kalıcı | `"el:yazma:C:\Users\ben\Projeler"` | `onay_defteri.json`'da durur; Ayarlar→El'den tek tek veya toplu iptal edilebilir |

Eylem türü sınıflandırması: `okuma` (serbest), `yazma` (yaz/düzelt/taşı),
`silme`, `calistirma` (program aç/kapat). Oturum/kalıcı izinler **eylem türü ×
bölge** çiftiyle eşleşir; daha geniş bölge izni alt bölgeleri de kapsar.

## 4. Zaman çizelgesi (askıda çalışma modeli)

1. Kullanıcı mesajı gönderir → `/api/sohbet`.
2. Karar merkezi `el` yeteneğini çağırır → El, kuyruğa `kimlik` ile kart koyar,
   yanıt metni + `onay` nesnesi panele döner. Mesaj **"yanit_gecici"** bayrağıyla
   kaydedilir (onay kesinleşince güncellenecek).
3. Panel kartı çizer; kullanıcı bir seçenek tıklar → `POST /api/onay_ver`
   `{kimlik, secenek}`.
4. Sunucu thread'i kuyrukta bekleyen El çağrısını uyandırır:
   - `evet/oturum/kalici` → eylem uygulanır, izin defteri güncellenir,
     sonuç metni üretilir.
   - `hayir` → "Reddedildi, eylem yapılmadı."
   - 300 sn sessizlik → `suresi_doldi`, eylem yapılmaz.
5. Sonuç: aynı sohbet baloncuğu güncellenir + sisteme otomatik kullanıcı-kök-lü
   bir not eklenir ("El işlemi tamamlandı: ...") ki **hafıza organı sonucu bilsin**.

## 5. Güvenlik notları

- Silme asla kalıcı değil → geri dönüşüm kutusu (`send2trash`), yoksa
  `veri/cikti/_el_cop/` klasörüne taşıma.
- Yazma/düzeltme öncesi gölge kopya → `veri/yedekler/el_zamani_dosyaAdi`.
- Her eylem ve her onay kararı `veri/gunlukler/el_gunlugu.jsonl`'a yazılır
  (kim, hangi eylem, hangi izin derecesi, sonucu).
- Onay kartındaki hedef yolu kullanıcı elle giremez; kart her zaman El'in
  çözümlediği gerçek mutlak yolu gösterir (path-trick önlemi).

## 6. Yeni API uçları (özet)

| Uç | İşlev |
|---|---|
| `GET /api/onaylar` | Bu oturumun bekleyen/onaylanmış kartları (yeniden yüklemede kartlar kaybolmasın diye) |
| `POST /api/onay_ver` | `{kimlik, secenek}` → kuyruğu uyandırır |
| `GET /api/el_izinleri` | İzin defterini listeler (Ayarlar→El ekranı) |
| `POST /api/el_izin_iptal` | Bir kaydı veya tümünü siler |
| `POST /api/el_bolge` | Yetkili bölge ekle/kaldır (ayar) |

## 7. Tartışmaya açık son kararlar (uygulamada şöyle kabul edildi)

- Oturum = tarayıcı oturum kimliği (`oid`). Panel yenilenince bekleyen kartlar
  `GET /api/onaylar` ile geri gelir; sayfa tamamen kapanırsa oturum izinleri düşer.
- Kalıcı izin istemi gelirse kullanıcı yine de "bu seferlik"i seçebilir;
  sistem kalıcıyı dayatmaz.
- `dosya_yazma` (eski basit El) emekliye ayrılır; yerine tam **EL** geçer.
