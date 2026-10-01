"use strict";

const state = {
  data: null, view: "regions", level: "district", exCenter: false, rooms: "all",
  parent: "", query: "", showThin: true, showCountyRent: false, sort: { key: "yield_median", dir: -1 },
};

const COUNTY_RENT_LEVELS = new Set(["county", "county_ex_center"]);

const LEVEL_NAMES = { county: "maakond", county_ex_center: "maakond v.a keskus", city: "linn/vald",
  district: "linnaosa", subdistrict: "asum" };

const pct = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const eur = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 0 });
const eur2 = new Intl.NumberFormat("et-EE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmt = (f, v) => (v === null || v === undefined ? "–" : f.format(v));
const $ = (id) => document.getElementById(id);

const COLUMNS = {
  regions: [
    { key: "name", label: "Piirkond", cell: (r) => esc(r.name) },
    { key: "parent", label: "Asukoht", cell: (r) => esc(r.parent), cls: "muted" },
    { key: "yield_median", label: "Tootlus", num: true, cell: (r) => fmt(pct, r.yield_median), cls: "strong" },
    { key: "yield_latest", label: "Viimane", num: true, cell: (r) => fmt(pct, r.yield_latest) },
    { key: "sale_m2", label: "Müük €/m²", num: true, cell: (r) => fmt(eur, r.sale_m2) },
    { key: "rent_m2", label: "Üür €/m²", num: true, cell: (r) => fmt(eur2, r.rent_m2) },
    { key: "n_sale", label: "Müük / üür", num: true, cell: (r) => `${r.n_sale} / ${r.n_rent}` },
    { key: "valid_runs", label: "Ajapunkte", num: true, cell: (r) => r.valid_runs },
  ],
  listings: [
    { key: "address", label: "Aadress", cell: (r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.address)}</a>` },
    { key: "parent", label: "Piirkond", cell: (r) => esc(r.parent), cls: "muted" },
    { key: "rooms", label: "Toad", num: true, cell: (r) => r.rooms },
    { key: "area_m2", label: "m²", num: true, cell: (r) => fmt(eur2, r.area_m2) },
    { key: "price", label: "Hind €", num: true, cell: (r) => fmt(eur, r.price) },
    { key: "rent_estimate", label: "Oodatav üür €", num: true, cell: (r) => fmt(eur, r.rent_estimate) },
    { key: "yield", label: "Tootlus", num: true, cell: (r) => fmt(pct, r.yield), cls: "strong" },
    { key: "rent_level", label: "Üür tasemelt", cell: (r) => LEVEL_NAMES[r.rent_level] || r.rent_level, cls: "muted" },
  ],
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function effectiveLevel() {
  return state.level === "county" && state.exCenter ? "county_ex_center" : state.level;
}

function regionRows() {
  const level = effectiveLevel();
  return state.data.regions
    .filter((r) => r.level === level && r.rooms === state.rooms)
    .map((r) => ({ ...r, parent: r.path.slice(0, -1).join(" › ") }));
}

function listingRows() {
  return state.data.listings
    .filter((r) => state.rooms === "all" || roomGroup(r.rooms) === state.rooms)
    .filter((r) => state.showCountyRent || !COUNTY_RENT_LEVELS.has(r.rent_level))
    .map((r) => ({ ...r, parent: r.path.join(" › ") }));
}

function roomGroup(n) { return n >= 4 ? "4+" : String(n); }

function rowsForView() {
  let rows = state.view === "regions" ? regionRows() : listingRows();
  if (state.parent) rows = rows.filter((r) => r.parent === state.parent || r.parent.startsWith(state.parent + " › "));
  if (state.query) {
    const q = state.query.toLocaleLowerCase("et");
    rows = rows.filter((r) => ((r.name || r.address) + " " + r.parent).toLocaleLowerCase("et").includes(q));
  }
  if (state.view === "regions" && !state.showThin) rows = rows.filter((r) => r.enough);
  const { key, dir } = state.sort;
  rows.sort((a, b) => {
    if (state.view === "regions" && a.enough !== b.enough) return a.enough ? -1 : 1;
    const x = a[key], y = b[key];
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    return (typeof x === "string" ? x.localeCompare(y, "et") : x - y) * dir;
  });
  return rows;
}

function parentOptions() {
  const rows = state.view === "regions" ? regionRows() : listingRows();
  const set = new Set();
  rows.forEach((r) => {
    const parts = r.parent.split(" › ").filter(Boolean);
    for (let i = 1; i <= parts.length; i++) set.add(parts.slice(0, i).join(" › "));
  });
  return [...set].sort((a, b) => a.localeCompare(b, "et"));
}

function renderParent() {
  const sel = $("parent");
  const opts = parentOptions();
  if (state.parent && !opts.includes(state.parent)) state.parent = "";
  sel.innerHTML = `<option value="">Kõik</option>` +
    opts.map((o) => `<option value="${esc(o)}"${o === state.parent ? " selected" : ""}>${esc(o)}</option>`).join("");
}

function render() {
  const cols = COLUMNS[state.view];
  const rows = rowsForView();
  document.querySelectorAll(".tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === state.view)));
  document.querySelectorAll(".f-level, .f-excenter").forEach((el) => (el.hidden = state.view !== "regions"));
  $("ex-center").disabled = state.level !== "county";
  $("show-thin").parentElement.hidden = state.view !== "regions";
  $("show-county-rent").parentElement.hidden = state.view !== "listings";
  renderParent();

  $("table").querySelector("thead").innerHTML = "<tr>" + cols.map((c) => {
    const active = state.sort.key === c.key;
    const aria = active ? (state.sort.dir > 0 ? "ascending" : "descending") : "none";
    return `<th class="${c.num ? "num" : ""}" aria-sort="${aria}"><button type="button" data-sort="${c.key}">${c.label}</button></th>`;
  }).join("") + "</tr>";

  $("table").querySelector("tbody").innerHTML = rows.map((r) =>
    `<tr class="${state.view === "regions" && !r.enough ? "thin" : ""}">` +
    cols.map((c) => `<td class="${[c.num ? "num" : "", c.cls || ""].join(" ")}">${c.cell(r)}</td>`).join("") + "</tr>"
  ).join("");

  $("empty").hidden = rows.length > 0;
  $("hint").textContent = state.view === "regions"
    ? `${rows.length} piirkonda · hallid read: alla 5 müügi- või üürikuulutuse`
    : `${rows.length} müügikuulutust viimasest käivitusest · oodatav üür piirkonna üüri €/m² mediaanist` +
      (state.showCountyRent ? "" : " · maakonna keskmise üüriga kuulutused on peidetud");
}

function renderMeta() {
  const runs = state.data.runs;
  if (!runs.length) { $("meta").textContent = "Andmeid pole veel kogutud."; return; }
  const last = runs[runs.length - 1];
  const when = new Date(last.started_at).toLocaleDateString("et-EE", { day: "numeric", month: "long", year: "numeric" });
  const partial = last.complete ? "" : ` · viimane käivitus osaline (${last.counties_ok.length} maakonda)`;
  $("meta").textContent = `Uuendatud ${when} · ${runs.length} ajapunkt${runs.length === 1 ? "" : "i"}${partial}`;
}

async function loadData() {
  const res = await fetch("data/results.json", { cache: "no-store" });
  state.data = res.ok ? await res.json() : { runs: [], regions: [], listings: [] };
  renderMeta();
  render();
}

async function pollStatus() {
  let status;
  try {
    const res = await fetch("api/status", { cache: "no-store" });
    if (!res.ok) return;
    status = await res.json();
  } catch { return; }
  $("run").hidden = false;
  $("run-btn").disabled = status.running;
  $("run-btn").textContent = status.running ? "Kogun…" : "Käivita uuesti";
  const last = status.messages[status.messages.length - 1];
  $("run-log").textContent = status.error ? `Viga: ${status.error}` : (status.running ? last || "Alustan…" : (status.finished_at ? "Valmis." : ""));
  if (status.running) setTimeout(pollStatus, 1500);
  else if (state.wasRunning) loadData();
  state.wasRunning = status.running;
}

function bind() {
  document.querySelectorAll(".tabs [role=tab]").forEach((b) => b.addEventListener("click", () => {
    state.view = b.dataset.view;
    state.parent = "";
    state.sort = { key: state.view === "regions" ? "yield_median" : "yield", dir: -1 };
    render();
  }));
  $("level").addEventListener("change", (e) => { state.level = e.target.value; state.parent = ""; render(); });
  $("ex-center").addEventListener("change", (e) => { state.exCenter = e.target.checked; render(); });
  $("rooms").addEventListener("change", (e) => { state.rooms = e.target.value; render(); });
  $("parent").addEventListener("change", (e) => { state.parent = e.target.value; render(); });
  $("query").addEventListener("input", (e) => { state.query = e.target.value.trim(); render(); });
  $("show-thin").addEventListener("change", (e) => { state.showThin = e.target.checked; render(); });
  $("show-county-rent").addEventListener("change", (e) => { state.showCountyRent = e.target.checked; render(); });
  $("table").querySelector("thead").addEventListener("click", (e) => {
    const key = e.target.closest("button")?.dataset.sort;
    if (!key) return;
    state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : (key === "name" || key === "address" || key === "parent" ? 1 : -1) };
    render();
    document.querySelector(`thead [data-sort="${key}"]`)?.focus();
  });
  $("run-btn").addEventListener("click", async () => {
    $("run-btn").disabled = true;
    await fetch("api/run", { method: "POST" });
    state.wasRunning = true;
    pollStatus();
  });
}

bind();
loadData();
pollStatus();
