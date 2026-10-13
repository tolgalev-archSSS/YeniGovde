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
  organDiv.innerHTML = ""; yetDiv.innerHTML = ""; hz.innerHTML = "";
  d.moduller.forEach(m => {
    const satir = document.createElement("div");
    satir.className = "modul-satir";
    const duruyor = m.tur === "organ" && d.calisan_organlar.includes(m.kod);
    satir.innerHTML =
      `<span class="tur tur-${m.tur}">${m.tur}</span>
       <span class="ad" title="${(m.aciklama || "") + (m.hata ? "\nHATA: " + m.hata : "")}">
         ${m.ad}${m.hata ? ' ⚠️' : ''}${duruyor ? ' 🟢' : ''}</span>
       <label class="switch"><input type="checkbox" ${m.etkin ? "checked" : ""}
         onchange="modulEtkin('${m.kod}','${m.tur}',this.checked)"><span class="slider"></span></label>`;
    (m.tur === "organ" ? organDiv : yetDiv).appendChild(satir);
    if (m.tur === "yetenek" && m.etkin) {
      const o = document.createElement("option");
      o.value = m.kod; o.textContent = m.ad; hz.appendChild(o);
    }
  });
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

/* ---------- açılış ---------- */
(async () => {
  await durumuCek();
  gecmisiYukle();
})();
