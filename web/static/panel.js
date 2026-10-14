/* ÜRETİM PANELİ — istemci mantığı (Türkçe) */
let aktifOturum = "genel";
let tarananModeller = [];

const $ = (id) => document.getElementById(id);

async function api(yol, options) {
  const r = await fetch(yol, options);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
const post = (yol, veri) => api(yol, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(veri || {})
});

/* ---------- durum / üst bar ---------- */
async function durumuCek() {
  try {
    const d = await api("/api/durum");
    $("n-oklama").className = "durum-nokta " + (d.ollama_canli ? "ok" : "kotu");
    const secildi = d.ayarlar.modeller.rutin_model && d.ayarlar.modeller.agir_model;
    $("n-model").className = "durum-nokta " + (secildi ? "ok" : "orta");
    tarananModeller = d.modeller || [];
    if (d.ollama_canli && !secildi && tarananModeller.length) otomatikModelOner(d.ayarlar);
    oturumlariYenile();
    modulleriYenile();
  } catch (e) { console.error(e); }
}
setInterval(() => { $("saat").textContent = new Date().toLocaleTimeString("tr-TR"); }, 1000);

/* En küçük model → rutin, en büyük → ağır, ortanca/uygun → sınıflandırma.
   Sadece hiç seçim yoksa ve kullanıcı onaylayınca kaydedilir (burada öneri). */
function otomatikModelOner(ayarlar) {
  const sirali = [...tarananModeller].sort((a, b) => a.boyut_gb - b.boyut_gb);
  ayarlar.modeller.rutin_model = sirali[0]?.ad || "";
  ayarlar.modeller.agir_model = sirali[sirali.length - 1]?.ad || "";
  ayarlar.modeller.siniflandirma_modeli = sirali[Math.max(0, Math.floor(sirali.length / 2))]?.ad || sirali[0]?.ad || "";
  bilgiGoster(
    "Ollama bağlantısı kuruldu ve yüklü modeller bulundu.\n\n" +
    "Boyuta göre ÖNERİLEN varsayılan atandı:\n" +
    "• Rutin (hafif işler): " + ayarlar.modeller.rutin_model + "\n" +
    "• Ağır (kod/planlama): " + ayarlar.modeller.agir_model + "\n" +
    "• Karar merkezi: " + ayarlar.modeller.siniflandirma_modeli + "\n\n" +
    "Ayarlar → Model ve Sistem Ayarları bölümünden değiştirip KAYDEDEBİLİRSİNİZ.",
    "İlk Kurulum");
  modalAc("modal-ayar");
  ayarlariDoldur(ayarlar);
}

/* ---------- modüller ---------- */
async function modulleriYenile() {
  const d = await api("/api/moduller");
  const organDiv = $("organ-liste"), yetDiv = $("yetenek-liste"), hz = $("hz-modul");
  const nodeDiv = $("node-liste") || document.createElement("div");
  organDiv.innerHTML = ""; yetDiv.innerHTML = ""; hz.innerHTML = ""; nodeDiv.innerHTML = "";
  d.moduller.forEach(m => {
    const satir = document.createElement("div");
    satir.className = "modul-satir";
    const duruyor = m.tur === "organ" && d.calisan_organlar.includes(m.kod);
    satir.innerHTML =
      `<span class="tur tur-${m.tur}">${m.tur}</span>
       <span class="ad" title="${(m.aciklama || "") + (m.hata ? "\nHATA: " + m.hata : "")}">
         ${m.ad}${m.hata ? ' ⚠️' : ''}${duruyor ? ' 🟢' : ''}</span>
       <label class="switch"><input type="checkbox" ${m.etkin ? "checked" : ""}
         onchange="modulEtkin('${m.kod}','${m.tur}',this.checked)"><span class="slider"></span></label>
       <button class="sok-btn" title="Çalıştırmeden çıkar; nodeller/kabul/ arşivine gider, oradan geri kurabilirsin"
         onclick="modulSok('${m.kod}','${m.tur}')">✂ Sök</button>`;
    if (m.tur === "organ") organDiv.appendChild(satir);
    else if (m.tur === "node") nodeDiv.appendChild(satir);
    else yetDiv.appendChild(satir);
    if ((m.tur === "yetenek" || m.tur === "node") && m.etkin) {
      const o = document.createElement("option");
      o.value = m.kod; o.textContent = m.ad; hz.appendChild(o);
    }
  });
}
async function modulSok(kod, tur) {
  if (!confirm(`"${kod}" (${tur}) sökülsün mü?\nKlasör SİLİNMEZ — nodeller/kabul/ içine taşınır ve Node Yönetimi'nden istediğin an geri kurabilirsin.`)) return;
  const d = await post("/api/modul_sok", { kod, tur });
  bilgiGoster(d.basarili ? ("Söküldü → " + (d.arsiv || "") + "\nKabul arşivinden geri kurabilirsin.")
                         : ("Hata: " + (d.neden || "?")), "Modül Sökme");
  modulleriYenile();
}
async function modulEtkin(kod, tur, etkin) {
  await post("/api/modul_etkinlik", { kod, tur, etkinlik: undefined, etkin });
  modulleriYenile();
}
async function hizliCagir() {
  const kod = $("hz-modul").value, girdi = $("hz-girdi").value;
  if (!kod) return;
  mesajEkle("user", "/" + kod + " " + girdi);
  const s = await post("/api/modul_cagir", { kod, girdi });
  mesajEkle("bot", s.yanit || s.hata || "(boş)", [{ adim: "doğrudan çağrı: " + kod }]);
}

/* ---------- GÖZ: ekran gözlemi (ekran_gozu node'u) ---------- */
let gozNobetci = false;

async function gozToggle() {
  const btn = $("btn-goz");
  if (gozNobetci) {   // ikinci tık: nöbetçiyi kapat
    const s = await post("/api/modul_cagir", { kod: "ekran_gozu", girdi: '{"eylem":"durdur"}' });
    gozNobetci = false;
    if (btn) { btn.textContent = "👁 Göz"; btn.classList.remove("agik"); }
    mesajEkle("bot", "👁 " + (s.yanit || "(kapandı)"), []);
    return;
  }
  // önce node takılı mı, araçlar ne âlemde — kontrol et
  const d = await post("/api/modul_cagir", { kod: "ekran_gozu", girdi: "izleme_durumu" })
              .catch(() => null);
  if (!d || d.hata) {
    alert("Göz henüz takılı değil.\nNode Yönetimi'nden 'ekran_gozu' node'unu kur ya da nodeller/kabul'dan onayla.");
    return;
  }
  mesajEkle("bot", "👁 GÖZ DURUMU: " + (d.yanit || ""), []);
  // tam ekrana bir kez bak (onay kartı çıkarsa aşağıdaki karttan yanıtla)
  const s = await post("/api/modul_cagir", { kod: "ekran_gozu", girdi: '{"eylem":"ekran_tara"}' });
  mesajEkle("bot", "👁 EKRAN GÖZÜM:\n" + (s.yanit || s.hata || "(boş)"), []);
  // nöbetçi başlat: ucuz değişim-piksel döngüsü (30 sn)
  const n = await post("/api/modul_cagir", { kod: "ekran_gozu", girdi: '{"eylem":"gozetle","sure_sn":30}' });
  if (n.basarili) {
    gozNobetci = true;
    if (btn) { btn.textContent = "👁 Göz AÇIK (kapat)"; btn.classList.add("agik"); }
    mesajEkle("bot", "👁 Nöbetçi: " + (n.yanit || "başladı") +
             "\n(Değişim raporlarını görmek için butona tekrar basınca son 10 rapor gelir.)", []);
  }
}

/* ---------- oturumlar ---------- */
async function oturumlariYenile() {
  const liste = await api("/api/sohbetler");
  const div = $("oturum-liste"); div.innerHTML = "";
  const hepsi = [{ oturum: "genel", mesaj_sayisi: 0 }].concat(liste.filter(l => l.oturum !== "genel"));
  hepsi.forEach(o => {
    const d = document.createElement("div");
    d.className = "oturum" + (o.oturum === aktifOturum ? " secili" : "");
    d.innerHTML = `<span>${o.oturum}</span><span>${o.mesaj_sayisi || 0} mesaj</span>`;
    d.onclick = async () => { aktifOturum = o.oturum; oturumlariYenile(); gecmisiYukle(); };
    div.appendChild(d);
  });
}
async function yeniOturum() {
  const ad = prompt("Oturum adı (boş bırakılabilir):") || "";
  const d = await post("/api/oturum_yeni", { ad });
  aktifOturum = d.oturum; oturumlariYenile();
  $("mesajlar").innerHTML = "";
}
async function gecmisiYukle() {
  const d = await api("/api/gecmis/" + aktifOturum);
  const div = $("mesajlar"); div.innerHTML = "";
  d.mesajlar.forEach(m => mesajEkle(m.rol === "user" ? "user" : "bot", m.icerik));
}

/* ---------- sohbet ---------- */
function mesajEkle(tip, metin, adimlar, karar, model) {
  const div = document.createElement("div");
  div.className = "mesaj " + tip + (tip === "bot" && !metin ? " hata" : "");
  let etiket = "";
  if (karar) {
    const agir = (karar.agirlik ?? 0) >= 0.55;
    etiket += `<span class="chip ${agir ? "agır".replace('ı','i') : "rutin"}">${agir ? "AĞIR" : "RUTİN"} · ağırlık ${karar.agirlik}</span>`;
    if (karar.modul && karar.modul !== "yok") etiket += `<span class="chip modul">⚡ ${karar.modul}</span>`;
    etiket += `<span class="chip">${karar.kaynak || ""}</span>`;
    if (model) etiket += `<span class="chip">🧠 ${model}</span>`;
  }
  let adimMetni = "";
  if (adimlar && adimlar.length) {
    adimMetni = "\n\n— Adımlar —\n" + adimlar.map(a =>
      "• " + a.adim + (a.sonuc ? ": " + String(a.sonuc).slice(0, 200) : "") +
      (a.hata ? " HATA: " + a.hata : "")).join("\n");
  }
  div.innerHTML = (etiket ? `<div class="etiket">${etiket}</div>` : "") +
    escapeHtml(metin || "(yanıt yok)" + adimMetni);
  $("mesajlar").appendChild(div);
  $("mesajlar").scrollTop = $("mesajlar").scrollHeight;
  return div;
}
function escapeHtml(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

async function mesajGonder() {
  const t = $("giris"); const metin = t.value.trim();
  if (!metin) return;
  t.value = "";
  mesajEkle("user", metin);
  $("yaziyor").classList.remove("kapali"); $("gonder").disabled = true;
  try {
    const d = await post("/api/sohbet", { mesaj: metin, oturum: aktifOturum });
    const yanit = d.yanit || d.hata || "(boş yanıt)";
    mesajEkle("bot", yanit, d.adimlar, d.karar, d.model);
    oturumlariYenile();
  } catch (e) {
    mesajEkle("bot", "İstek başarısız: " + e, [], null, null);
  } finally {
    $("yaziyor").classList.add("kapali"); $("gonder").disabled = false; t.focus();
  }
}
$("giris").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); mesajGonder(); }
});

/* ---------- ayarlar ---------- */
function ayarlariDoldur(a) {
  $("ay-adres").value = a.ollama.adres;
  $("ay-esik").value = a.modeller.guc_orani;
  $("hf-etkin").checked = !!a.hafiza.etkin;
  $("hf-motor").value = a.hafiza.motor;
  $("hf-pencere").value = a.hafiza.pencere_mesaj;
  $("hf-esik").value = a.hafiza.oturum_basina_ozet;
  modelSecenekleriniDoldur(tarananModeller);
  $("ay-rutin").value = a.modeller.rutin_model;
  $("ay-agir").value = a.modeller.agir_model;
  $("ay-sinif").value = a.modeller.siniflandirma_modeli;
}
function modelSecenekleriniDoldur(modeller) {
  const div = $("model-liste"); div.innerHTML = "";
  ["ay-rutin", "ay-agir", "ay-sinif"].forEach(id => $(id).innerHTML = "<option value=''>— seçilmedi —</option>");
  modeller.forEach(m => {
    ["ay-rutin", "ay-agir", "ay-sinif"].forEach(id => {
      const o = document.createElement("option");
      o.value = m.ad; o.textContent = `${m.ad} (${m.boyut_gb} GB · ${m.parametre})`;
      $(id).appendChild(o);
    });
    const k = document.createElement("div");
    k.className = "model-kart";
    k.innerHTML = `<b style="flex:1">${m.ad}</b><span>${m.boyut_gb} GB</span>
      <span>${m.parametre}</span><button class="btn gris kucuk" onclick="modelTestAdi('${m.ad}')">Test</button>`;
    div.appendChild(k);
  });
}
async function ollamaTara() {
  await post("/api/ayarlar", { ollama: { adres: $("ay-adres").value } });
  const d = await api("/api/durum");
  tarananModeller = d.modeller || [];
  modelSecenekleriniDoldur(tarananModeller);
  $("test-sonuc").textContent = d.ollama_canli
    ? `Bağlantı OK · sürüm ${d.ollama_surum} · ${tarananModeller.length} model bulundu.`
    : "Bağlantı kurulamadı: " + d.hata;
}
async function modelTest(selectId) { modelTestAdi($(selectId).value); }
async function modelTestAdi(ad) {
  if (!ad) return;
  $("test-sonuc").textContent = "'" + ad + "' deneniyor…";
  const s = await post("/api/model_test", { model: ad });
  $("test-sonuc").textContent = s.basarili
    ? `'${ad}' ÇALIŞIYOR (${s.sure_sn} sn, örnek: "${s.ornek}")`
    : `'${ad}' HATA: ${s.hata}`;
}
async function ayarKaydet() {
  await post("/api/ayarlar", {
    ollama: { adres: $("ay-adres").value },
    modeller: {
      rutin_model: $("ay-rutin").value,
      agir_model: $("ay-agir").value,
      siniflandirma_modeli: $("ay-sinif").value,
      guc_orani: parseFloat($("ay-esik").value) || 0.55
    }
  });
  alert("Kaydedildi. Seçimler sonraki açılışta varsayılan olacak.");
  modalKapat("modal-ayar"); durumuCek();
}
async function hafizaKaydet() {
  await post("/api/ayarlar", {
    hafiza: {
      etkin: $("hf-etkin").checked, motor: $("hf-motor").value,
      pencere_mesaj: parseInt($("hf-pencere").value) || 12,
      oturum_basina_ozet: parseInt($("hf-esik").value) || 8
    }
  });
  alert("Hafıza ayarları kaydedildi."); modalKapat("modal-hafiza");
}
async function hafizaOzetGoster() {
  const d = await api("/api/ozet/" + aktifOturum);
  bilgiGoster("== Oturum çalışma notu (" + aktifOturum + ") ==\n" +
    (d.oturum_ozeti || "(henüz özet yok — arka plan özetleyicisi eşik dolunca çalışır)") +
    "\n\n== Kalıcı bellek ==\n" + (d.kalici_bellek || "(boş)"), "Hafıza");
}

/* ---------- modal ---------- */
function modalAc(id) { $(id).classList.add("acik"); }
function modalKapat(id) { $(id).classList.remove("acik"); }
function bilgiGoster(metin, baslik) {
  $("bilgi-icerik").textContent = metin;
  $("bilgi-baslik").textContent = baslik || "Bilgi";
  modalAc("modal-bilgi");
}
document.querySelectorAll(".modal-arka").forEach(m =>
  m.addEventListener("click", e => { if (e.target === m) m.classList.remove("acik"); }));

/* ---------- onay kartları (kapıcı) ---------- */
let aktifKart = null, kalanSn = 0, sayacTimer = null;

async function onaylariYokla() {
  try {
    const d = await api("/api/onaylar");
    if (!aktifKart && d.bekleyenler.length) {
      aktifKart = d.bekleyenler[0];
      kalanSn = d.sure_sn || 300;
      onayKartGoster();
    }
    if (aktifKart && !d.bekleyenler.some(k => k.kimlik === aktifKart.kimlik)) {
      // kart zaman aşımına uğradı veya başka yoldan kararlaştı
      onayKartKapat();
    }
  } catch (e) { /* sunucu henüz hazır değil */ }
}
function onayKartGoster() {
  $("onay-baslik").textContent = "🔐 Onay bekliyor: " + aktifKart.eylem;
  $("onay-aciklama").textContent = aktifKart.aciklama || "";
  $("onay-hedef").textContent = "Hedef: " + (aktifKart.hedef || "-") +
    "  ·  Alan: " + (aktifKart.alan || "*") + "  ·  İstek: " + aktifKart.istek_zamani;
  $("onay-kart").classList.add("acik");
  clearInterval(sayacTimer);
  sayacTimer = setInterval(() => {
    kalanSn--;
    $("onay-sayac").textContent = "Kalan süre: " + Math.max(0, kalanSn) + " sn";
    if (kalanSn <= 0) onayKartKapat();
  }, 1000);
}
function onayKartKapat() {
  clearInterval(sayacTimer); $("onay-kart").classList.remove("acik");
  aktifKart = null;
}
async function onayVer(secenek) {
  if (!aktifKart) return;
  const d = await post("/api/onay_ver", { kimlik: aktifKart.kimlik, secenek });
  if (!d.basarili) bilgiGoster(d.neden || "Kart bulunamadı.", "Onay");
  onayKartKapat();
}
setInterval(onaylariYokla, 2000);

/* ---------- arka plan sonuçları (araştırmacı/el) ---------- */
async function sonuclariYokla() {
  try {
    const d = await api("/api/sonuclar_bekleyen?oturum=" + encodeURIComponent(aktifOturum));
    for (const s of d.sonuclar || []) {
      mesajEkle("bot", s.yanit || ("⚠️ " + (s.hata || "(boş sonuç)")),
                s.adimlar, s.karar, s.model);
      await post("/api/gecmis_yaz", { oturum: aktifOturum,
        icerik: s.yanit || ("HATA: " + (s.hata || "")), model: s.model || "" });
    }
    if ((d.sonuclar || []).length) oturumlariYenile();
  } catch (e) { /* sessiz */ }
}
setInterval(sonuclariYokla, 3000);

/* ---------- arama ayarları ---------- */
async function aramaAyarGoster() {
  const a = await api("/api/ayarlar");
  $("ar-serbest").checked = !!a.arama.onay_serbest;
  $("ar-ingilizce").checked = a.arama.ingilizce_ara !== false;
  $("ar-adet").value = a.arama.varsayilan_adet || 6;
  $("ar-guncelveri").checked = a.arama.guncel_veri_birimi_acik !== false;
  const siteler = a.arama.site_onceligi || [];
  $("ar-siteler").value = siteler.join(", ");
  $("ar-site-oncelik").checked = siteler.length > 0;
  modalAc("modal-arama");
}
async function aramaKaydet() {
  let siteler = [];
  if ($("ar-site-oncelik").checked)
    siteler = $("ar-siteler").value.split(",").map(s => s.trim()).filter(Boolean);
  await post("/api/ayarlar", { arama: {
    onay_serbest: $("ar-serbest").checked,
    ingilizce_ara: $("ar-ingilizce").checked,
    varsayilan_adet: parseInt($("ar-adet").value) || 6,
    guncel_veri_birimi_acik: $("ar-guncelveri").checked,
    site_onceligi: siteler
  }});
  alert("Arama ayarları kaydedildi."); modalKapat("modal-arama");
}

/* ---------- sökülen arşivi / izin defteri ---------- */
async function sokulenleriGoster() {
  const d = await api("/api/modul_sokulenler");   // yeni yer: nodeller/kabul/
  const div = $("arsiv-liste"); div.innerHTML = "";
  if (!d.sokulenler || !d.sokulenler.length)
    { div.textContent = "Kabul arşivi boş — hiç sökülmüş/dışarıdan yazılmış modül yok."; }
  d.sokulenler.forEach(m => {
    const k = document.createElement("div"); k.className = "model-kart";
    k.innerHTML = `<b style="flex:1">${m.arsiv_adi}</b><span>${m.tur}</span>
      <button class="btn kucuk" onclick="geriKur('${m.kod}','${m.tur}')">↩ Geri Kur</button>`;
    div.appendChild(k);
  });
  modalAc("modal-arsiv");
}
async function geriKur(kod, tur) {
  const d = await post("/api/modul_geri_kur", { kod, tur });
  bilgiGoster(d.basarili ? `"${kod}" geri takıldı (${d.yol}).`
                         : ("Hata: " + (d.neden || d.hata || "?")), "Geri Kurma");
  modulleriYenile(); sokulenleriGoster();
}

/* ---------- NODE YÖNETİMİ (Ayarlar menüsü) ---------- */
async function nodeYonetimiGoster() {
  const d = await api("/api/node_listesi");
  const yk = $("node-yuklu"), kb = $("node-kabul"), es = $("node-eski");
  yk.innerHTML = ""; kb.innerHTML = ""; es.innerHTML = "";
  if (!d.yuklu.length) yk.innerHTML = "<div class='not'>(yüklü node yok)</div>";
  d.yuklu.forEach(n => {
    const k = document.createElement("div"); k.className = "model-kart";
    k.innerHTML =
      `<b style="flex:1">${n.ad || n.kod}</b>
       <span class="tur tur-node" style="background:#12303f;color:var(--vurgu)">node ${n.surum}</span>
       <span title="${(n.aciklama||'').replace(/"/g,'&quot;')}">${n.etkin ? "🟢 etkin" : "⚪ pasif"}${n.hata ? " ⚠️" : ""}</span>
       <label class="switch"><input type="checkbox" ${n.etkin ? "checked" : ""}
         onchange="modulEtkin('${n.kod}','node',this.checked);nodeYonetimiGoster()"><span class="slider"></span></label>
       <button class="sok-btn" onclick="modulSok('${n.kod}','node');setTimeout(nodeYonetimiGoster,400)">✂ Sök</button>`;
    yk.appendChild(k);
  });
  if (!d.kabul.length) kb.innerHTML = "<div class='not'>(kabul klasörü boş — dışarıdan yazdığınız ya da söktüğünüz node'lar burada bekler)</div>";
  d.kabul.forEach(c => {
    const k = document.createElement("div"); k.className = "model-kart";
    k.innerHTML =
      `<b style="flex:1">${c.arsiv_adi}</b>
       <span>${c.hazir ? "✅ paket hazır" : "⚠️ modul.py yok"}</span>
       <button class="btn kucuk" ${c.hazir ? "" : "disabled"}
         onclick="nodeOnayla('${c.arsiv_adi}')">✔ Onayla & Kur</button>
       <button class="btn gris kucuk" onclick="geriKur('${c.kod}','node')">↩ Eski yerine</button>`;
    kb.appendChild(k);
  });
  if (d.eski_arsiv && d.eski_arsiv.length) {
    es.innerHTML = `<div class="not">⚠ Eski 'veri/sokulen_moduller' arşivinde ${d.eski_arsiv.length} kayıt var — yukarıdaki düğmeyle KABUL'e taşıyabilirsiniz.</div>`;
  } else { es.innerHTML = ""; }
  modalAc("modal-node");
}
async function nodeOnayla(ad) {
  const d = await post("/api/node_onayla", { dosya: ad });
  bilgiGoster(d.basarili ? (d.yanit || "Kurulum tamam.")
                         : ("Reddedildi: " + (d.neden || d.hata || "?")), "Node Onayı");
  modulleriYenile(); nodeYonetimiGoster();
}
async function eskiArsiviKabuleTasi() {
  const d = await post("/api/eski_arsivi_kabule_tasi", {});
  bilgiGoster(d.basarili
    ? `${(d.tasinan || []).length} kayıt nodeller/kabul/'e taşındı.`
    : ("Hata: " + (d.neden || "?")), "Arşiv Göçü");
  nodeYonetimiGoster();
}

async function elIzinleriGoster() {
  const d = await api("/api/el_izinleri");
  let html = "<h4>Kalıcı izinler</h4>";
  if (!d.kalici.length) html += "<div class='not'>(yok)</div>";
  d.kalici.forEach(p => {
    html += `<div class="model-kart"><b style="flex:1">${p.eylem} @ ${p.alan}</b>
      <span>${p.eklendi || ""}</span>
      <button class="btn reddet kucuk" onclick="izinIptal('${p.anahtar}')">İptal</button></div>`;
  });
  html += "<h4>Bu oturumun izinleri</h4>";
  if (!d.oturum.length) html += "<div class='not'>(yok)</div>";
  d.oturum.forEach(a => { html += `<div class="model-kart"><b style="flex:1">${a}</b></div>`; });
  $("izin-liste").innerHTML = html;
  modalAc("modal-izinler");
}
async function izinIptal(anahtar) {
  await post("/api/el_izin_iptal", { anahtar }); elIzinleriGoster();
}
async function tumIzinleriSil() {
  if (!confirm("Tüm kalıcı izinler silinsin mi?")) return;
  const d = await api("/api/el_izinleri");
  for (const p of d.kalici) await post("/api/el_izin_iptal", { anahtar: p.anahtar });
  elIzinleriGoster();
}

/* ---------- üst panel: hava + kur (SADECE ilk açılışta çekilir) ---------- */
let kurCache = {};   // {USD: 49.38, EUR: ..., GBP: ...} — açılış anlık değeri

async function pencereVerisiCek() {
  try {
    const d = await api("/api/pencere_veri?sehir=istanbul");
    const h = (d.hava || [])[0];
    if (h) $("p-hava").textContent = "🌦 " + (h.baslik || "") + " · " +
      String(h.ozet || "").slice(0, 90);
    // guncel_veri_birimi başlık formatı: "1 USD = 49.38 TL"
    (d.kur || []).forEach(k => {
      const m = /1\s+(\w{3})\s*=\s*([\d.,]+)\s*TL/.exec(k.baslik || "");
      if (m) kurCache[m[1]] = parseFloat(m[2].replace(",", "."));
    });
    if (kurCache.USD) $("p-kur").textContent = "💵 $" + kurCache.USD.toFixed(2) + " TL";
  } catch (e) {
    $("p-hava").textContent = "🌦 veri yok"; $("p-kur").textContent = "💵 ?";
  }
}

async function dovusHesapla() {
  const miktar = parseFloat($("p-dovus").value);
  const tur = $("p-doviz-turu").value;
  const sonuc = $("p-dovus-sonuc");
  if (!(miktar > 0)) { sonuc.textContent = "bir sayı gir"; return; }
  sonuc.textContent = "…";
  try {
    let d;
    if (kurCache[tur]) {
      // açılışta çekilen anlık kur ile hesapla (sunucuya gitmez)
      d = { basarili: true, tl: miktar * kurCache[tur],
            zaman: "açılış kuru " + kurCache[tur].toFixed(4) };
    } else {
      d = await post("/api/dovus_hesapla", { miktar, para: tur });
      if (d.basarili && d.kur) kurCache[tur] = d.kur;
    }
    sonuc.textContent = d.basarili
      ? `${miktar} ${tur} = ${d.tl.toFixed(2)} TL (${d.zaman || ""})`
      : ("hata: " + (d.hata || "?"));
  } catch (e) { sonuc.textContent = "hata: " + e.message; }
}

/* ---------- açılış ---------- */
(async () => {
  pencereVerisiCek();          // hava+kur: bir kez, bekletmeden
  await durumuCek();
  gecmisiYukle();
  onaylariYokla();
})();
