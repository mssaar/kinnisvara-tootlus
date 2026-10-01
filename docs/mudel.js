"use strict";

const VABADUSE = [59.4339, 24.7445];
const pct = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pct2 = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const eur = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 0 });
const num1 = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 1 });
const num2 = new Intl.NumberFormat("et-EE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https:\/\//.test(u || "") ? u : "#");
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmtPct = (v) => (v == null ? "–" : pct.format(v));

const state = { data: null, rooms: "all", sortSub: { key: "residual_median", dir: 1 }, sortList: { key: "residual", dir: 1 } };

function roomGroup(n) { return n >= 4 ? "4+" : String(n); }

// Diverging: negatiivne hälve (alahinnatud) -> --good (sinine), positiivne -> --bad (oranž)
function divergingColor(v) {
  const t = Math.max(-1, Math.min(1, v / 0.2));
  return t <= 0 ? mix(css("--neutral"), css("--good"), -t) : mix(css("--neutral"), css("--bad"), t);
}
function mix(a, b, t) {
  const pa = hex(a), pb = hex(b);
  return `rgb(${pa.map((x, i) => Math.round(x + (pb[i] - x) * t)).join(",")})`;
}
function hex(h) { const m = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(m.slice(i, i + 2), 16)); }

function renderStats() {
  const d = state.data, last = d.runs[d.runs.length - 1], med = d.median || { effects: last.effects };
  const eff = (deal, km) => pct2.format(med.effects[deal][km]);
  $("meta").textContent = `Keskpunkt ${eur.format(last.center_offset_m)} m Vabaduse väljakust · ${d.runs.length} ajapunkt${d.runs.length === 1 ? "" : "i"} · ` +
    `${last.n.sale} müügi- ja ${last.n.rent} üürikuulutust` + (last.n.not_geocoded ? ` · ${last.n.not_geocoded} ilma koordinaatideta` : "");
  $("stats").innerHTML = ["1", "3", "6"].map((km) => `
    <div class="stat"><span class="stat-k">${km} km kaugusel, +100 m</span>
      <span class="stat-v">müük ${eff("sale", km)}</span><span class="stat-v2">üür ${eff("rent", km)}</span></div>`).join("") +
    `<div class="stat"><span class="stat-k">Mudeli R²</span><span class="stat-v">müük ${num2.format(last.r2.sale)}</span>
      <span class="stat-v2">üür ${num2.format(last.r2.rent)}</span></div>`;
}

function renderMap() {
  const d = state.data, center = (d.median && d.median.center) || d.runs[d.runs.length - 1].center;
  const map = L.map("map", { scrollWheelZoom: false }).setView([center.lat, center.lon], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  d.subdistricts.filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lon)).forEach((s) => {
    L.circle([s.lat, s.lon], { radius: 120 + Math.sqrt(s.n) * 60, color: css("--surface"), weight: 1, fillColor: divergingColor(s.residual_median), fillOpacity: 0.7 })
      .bindTooltip(`${esc(s.name)}: ${fmtPct(s.residual_median)} mudelist (${s.n} kuulutust)`).addTo(map);
  });
  d.listings.filter((l) => Number.isFinite(l.lat) && Number.isFinite(l.lon)).forEach((l) => {
    L.circleMarker([l.lat, l.lon], { radius: 4, color: css("--surface"), weight: 1.5, fillColor: css("--good"), fillOpacity: 1 })
      .bindPopup(`<a href="${esc(safeUrl(l.url))}" target="_blank" rel="noopener">${esc(l.address)}</a><br>` +
        `${eur.format(l.price)} € · mudel ${eur.format(l.predicted_price)} € (${fmtPct(l.residual)})`).addTo(map);
  });
  L.circleMarker(VABADUSE, { radius: 6, color: css("--muted"), weight: 2, dashArray: "3", fillOpacity: 0 })
    .bindTooltip("Vabaduse väljak").addTo(map);
  L.circleMarker([center.lat, center.lon], { radius: 9, color: css("--ink"), weight: 3, fillOpacity: 0 })
    .bindTooltip("Andmetest leitud keskpunkt").addTo(map);
  $("legend").innerHTML =
    `<span class="ramp">Asum (hind mudeli suhtes): <span>odavam</span><span class="bar" aria-hidden="true"></span><span>kallim</span></span>` +
    `<span>Täpid = alahinnatud kuulutused · paks ring = andmetest leitud keskpunkt · katkendlik ring = Vabaduse väljak</span>`;
}

function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw)), m = raw / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

function renderChart(svgId, key, fmt) {
  const svg = $(svgId), curve = (state.data.curve || []).filter((c) => Number.isFinite(c[key]) && Number.isFinite(c.d));
  svg.closest("figure").hidden = !curve.length;
  if (!curve.length) return;
  const W = Math.max(260, Math.round(svg.getBoundingClientRect().width) || 480), H = 220, P = { l: 48, r: 14, t: 10, b: 30 };
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const ys = curve.map((c) => c[key]), yMax = Math.max(...ys) * 1.05, yMin = Math.min(...ys) * 0.9;
  const x = (d) => P.l + (d / 15) * (W - P.l - P.r);
  const y = (v) => H - P.b - ((v - yMin) / (yMax - yMin)) * (H - P.t - P.b);
  const path = curve.map((c, i) => `${i ? "L" : "M"}${x(c.d).toFixed(1)},${y(c[key]).toFixed(1)}`).join("");
  const step = niceStep((yMax - yMin) / 3);
  const yTicks = [];
  for (let v = Math.ceil(yMin / step) * step; v <= yMax; v += step) yTicks.push(v);
  svg.setAttribute("aria-label", `${key === "sale_m2" ? "Müügi" : "Üüri"} €/m² muutub ${fmt(ys[0])} pealt ${fmt(ys[ys.length - 1])} peale 0–15 km jooksul`);
  svg.innerHTML =
    yTicks.map((v) => `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}" class="grid"/>` +
      `<text x="${P.l - 6}" y="${y(v) + 4}" class="tick" text-anchor="end">${fmt(v)}</text>`).join("") +
    [0, 5, 10, 15].map((d) => `<text x="${x(d)}" y="${H - 8}" class="tick" text-anchor="${d === 15 ? "end" : d === 0 ? "start" : "middle"}">${d} km</text>`).join("") +
    `<path d="${path}" class="line"/>`;
}

function sortRows(rows, { key, dir }) {
  return rows.sort((a, b) => {
    const p = a[key], q = b[key];
    if (p == null) return 1;
    if (q == null) return -1;
    return (typeof p === "string" ? p.localeCompare(q, "et") : p - q) * dir;
  });
}

const SUB_COLS = [
  { key: "name", label: "Asum", cell: (r) => esc(r.name) },
  { key: "residual_median", label: "Hind mudeli suhtes", num: true, cell: (r) => fmtPct(r.residual_median) },
  { key: "n", label: "Kuulutusi", num: true, cell: (r) => r.n },
];
const LIST_COLS = [
  { key: "address", label: "Aadress", cell: (r) => `<a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${esc(r.address)}</a>` },
  { key: "subdistrict", label: "Asum", cell: (r) => esc(r.subdistrict) },
  { key: "rooms", label: "Toad", num: true, cell: (r) => r.rooms },
  { key: "price", label: "Hind €", num: true, cell: (r) => eur.format(r.price) },
  { key: "predicted_price", label: "Mudel €", num: true, cell: (r) => eur.format(r.predicted_price) },
  { key: "residual", label: "Erinevus", num: true, cell: (r) => fmtPct(r.residual) },
  { key: "yield", label: "Tootlus (mudel)", num: true, cell: (r) => fmtPct(r.yield) },
];

function renderTable(id, cols, rows, sortState, onSort) {
  const t = $(id);
  t.querySelector("thead").innerHTML = "<tr>" + cols.map((c) => {
    const aria = sortState.key === c.key ? (sortState.dir > 0 ? "ascending" : "descending") : "none";
    return `<th class="${c.num ? "num" : ""}" aria-sort="${aria}"><button type="button" data-sort="${c.key}">${c.label}</button></th>`;
  }).join("") + "</tr>";
  t.querySelector("tbody").innerHTML = rows.length
    ? rows.map((r) => "<tr>" + cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.cell(r)}</td>`).join("") + "</tr>").join("")
    : `<tr><td colspan="${cols.length}" class="muted">Sobivaid ridu pole.</td></tr>`;
  t.querySelector("thead").onclick = (e) => {
    const key = e.target.closest("button")?.dataset.sort;
    if (!key) return;
    onSort(key);
    $(id).querySelector(`thead [data-sort="${key}"]`)?.focus();
  };
}

function renderTables() {
  const toggle = (s, key) => ({ key, dir: s.key === key ? -s.dir : 1 });
  renderTable("t-sub", SUB_COLS, sortRows([...state.data.subdistricts], state.sortSub), state.sortSub,
    (key) => { state.sortSub = toggle(state.sortSub, key); renderTables(); });
  const list = state.data.listings.filter((l) => state.rooms === "all" || roomGroup(l.rooms) === state.rooms);
  renderTable("t-list", LIST_COLS, sortRows([...list], state.sortList), state.sortList,
    (key) => { state.sortList = toggle(state.sortList, key); renderTables(); });
}

async function load() {
  let data = null;
  try {
    const res = await fetch("data/model.json", { cache: "no-store" });
    if (res.ok) data = await res.json();
  } catch { /* tühi olek allpool */ }
  if (!data || !data.runs || !data.runs.length) {
    $("meta").textContent = "Mudelit pole veel arvutatud.";
    $("empty").hidden = false;
    return;
  }
  state.data = data;
  $("content").hidden = false;
  renderStats();
  renderCharts();
  renderTables();
  try {
    if (typeof L === "undefined") throw new Error("Leaflet puudub");
    renderMap();
  } catch {
    $("map").textContent = "Kaarti ei õnnestunud laadida.";
    $("map").style.cssText = "display:grid;place-items:center;height:auto;min-height:80px;color:var(--muted)";
  }
}

function renderCharts() {
  renderChart("chart-sale", "sale_m2", (v) => eur.format(v));
  renderChart("chart-rent", "rent_m2", (v) => num1.format(v));
}
let resizeT;
window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => state.data && renderCharts(), 150); });

$("rooms").addEventListener("change", (e) => { state.rooms = e.target.value; renderTables(); });
load();
