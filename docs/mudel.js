"use strict";

const VABADUSE = [59.4339, 24.7445];
const pct = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pct2 = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pctTick = new Intl.NumberFormat("et-EE", { style: "percent", maximumFractionDigits: 0, signDisplay: "exceptZero" });
const eur = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 0 });
const num1 = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 1 });
const num2 = new Intl.NumberFormat("et-EE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https:\/\//.test(u || "") ? u : "#");
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmtPct = (v) => (v == null ? "–" : pct.format(v));
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const PRICE_STEP = 5000;
const ROOMS_MAX = 5; // 5 = "5+"
const UNDERVALUED = -0.15;

const state = {
  data: null, sortSub: { key: "residual_median", dir: 1 }, sortList: { key: "residual", dir: 1 },
  bounds: null, filter: null, scales: null, map: null, dotLayer: null, circles: [],
};

// --- Värviskaala: pidev interpolatsioon OKLab-ruumis CSS-is dokumenteeritud peatuste vahel ---

function hexToRgb(h) { const m = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(m.slice(i, i + 2), 16) / 255); }
const toLin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const fromLin = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
function rgbToOklab([r, g, b]) {
  [r, g, b] = [r, g, b].map(toLin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}
function oklabToCss([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
  return `rgb(${rgb.map((c) => Math.round(Math.max(0, Math.min(1, fromLin(c))) * 255)).join(",")})`;
}

// Skaala peatustest: t ∈ [0, 1] -> värv (peatused võrdsete vahedega)
function ramp(hexes) {
  const labs = hexes.map((h) => rgbToOklab(hexToRgb(h)));
  return (t) => {
    const x = Math.max(0, Math.min(1, t)) * (labs.length - 1), i = Math.min(labs.length - 2, Math.floor(x)), f = x - i;
    return oklabToCss(labs[i].map((v, k) => v + (labs[i + 1][k] - v) * f));
  };
}
const gradient = (fn) => `linear-gradient(90deg, ${Array.from({ length: 13 }, (_, i) => fn(i / 12)).join(", ")})`;

function quantile(values, q) {
  const s = [...values].sort((a, b) => a - b);
  if (!s.length) return null;
  const pos = (s.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

// Domeenid andmetest: asumid sümmeetriline ±d (|mediaanhälbe| 95. protsentiil, üles 1%-ni, vähemalt 5%);
// kuulutuste täpid järjestikune -15% ... hälvete 5. protsentiil
function computeScales() {
  const d = state.data;
  const p95 = quantile(d.subdistricts.map((s) => Math.abs(s.residual_median)).filter(Number.isFinite), 0.95) ?? 0;
  const div = Math.max(0.05, Math.ceil(Math.round(p95 * 1e4) / 100) / 100);
  let p5 = quantile(d.listings.map((l) => l.residual).filter(Number.isFinite), 0.05) ?? UNDERVALUED - 0.1;
  if (p5 > UNDERVALUED - 0.01) p5 = UNDERVALUED - 0.01;
  const dv = ramp([1, 2, 3, 4, 5, 6, 7].map((i) => css(`--div-${i}`)));
  const sq = ramp([1, 2, 3, 4].map((i) => css(`--seq-${i}`)));
  return {
    div, low: p5, divRamp: dv, seqRamp: sq,
    subColor: (v) => dv((v / div + 1) / 2),
    dotColor: (v) => sq((UNDERVALUED - v) / (UNDERVALUED - p5)),
  };
}

// --- Filtrid ---

const roomValue = (n) => (n == null ? null : Math.max(1, Math.min(ROOMS_MAX, n)));
const roomsText = (v) => (v >= ROOMS_MAX ? `${ROOMS_MAX}+` : String(v));

function computeBounds() {
  const L = state.data.listings;
  const prices = L.map((l) => l.price).filter(Number.isFinite);
  const floors = L.map((l) => l.floor).filter(Number.isFinite);
  const names = new Set([...L.map((l) => l.subdistrict), ...state.data.subdistricts.map((s) => s.name)].filter(Boolean));
  const lo = prices.length ? Math.floor(Math.min(...prices) / PRICE_STEP) * PRICE_STEP : 0;
  const hi = prices.length ? Math.ceil(Math.max(...prices) / PRICE_STEP) * PRICE_STEP : PRICE_STEP;
  return {
    rooms: [1, ROOMS_MAX],
    price: [lo, Math.max(hi, lo + PRICE_STEP)],
    floor: [Math.min(1, ...floors), Math.max(1, ...floors)],
    asums: [...names].sort((a, b) => a.localeCompare(b, "et-EE")),
  };
}

function defaultFilter() {
  const b = state.bounds;
  return { rooms: [...b.rooms], price: [...b.price], floor: [...b.floor], notFirst: false, notLast: false, asum: "" };
}

function passes(l) {
  const f = state.filter, b = state.bounds;
  const r = roomValue(l.rooms);
  if (r == null ? (f.rooms[0] !== b.rooms[0] || f.rooms[1] !== b.rooms[1]) : (r < f.rooms[0] || r > f.rooms[1])) return false;
  if (l.price < f.price[0] || l.price > f.price[1]) return false;
  if (f.asum && l.subdistrict !== f.asum) return false;
  if (l.floor == null) return true; // teadmata korrusega kuulutus jääb alati nähtavale
  if (l.floor < f.floor[0] || l.floor > f.floor[1]) return false;
  if (f.notFirst && l.floor === 1) return false;
  if (f.notLast && l.floors_total != null && l.floor === l.floors_total) return false;
  return true;
}

const filtered = () => (state.filter ? state.data.listings.filter(passes) : []);

// Kahe käepidemega vahemikuliugur: kaks kattuvat <input type=range>, mõlemal oma silt ja klaviatuur
function makeRange(el, { key, label, unit, step, fmt, text }) {
  const [min, max] = state.bounds[key];
  el.innerHTML = `
    <div class="range-head"><span class="range-label" id="${el.id}-l">${label}</span>
      <output class="range-out" id="${el.id}-o" for="${el.id}-a ${el.id}-b"></output></div>
    <div class="range-track">
      <input type="range" id="${el.id}-a" min="${min}" max="${max}" step="${step}" aria-label="${label}, alates">
      <input type="range" id="${el.id}-b" min="${min}" max="${max}" step="${step}" aria-label="${label}, kuni">
    </div>`;
  const a = $(`${el.id}-a`), b = $(`${el.id}-b`), out = $(`${el.id}-o`), track = el.querySelector(".range-track");
  const sync = () => {
    const [lo, hi] = state.filter[key];
    a.value = lo; b.value = hi;
    a.setAttribute("aria-valuetext", `${fmt(lo)} ${unit}`.trim());
    b.setAttribute("aria-valuetext", `${fmt(hi)} ${unit}`.trim());
    out.textContent = text(lo, hi);
    const span = max - min || 1;
    track.style.setProperty("--lo", `${((lo - min) / span) * 100}%`);
    track.style.setProperty("--hi", `${((hi - min) / span) * 100}%`);
    // Kokkulangevad käepidemed: "alates" on peal, nii saab need alati lahku tõmmata
    a.classList.toggle("on-top", lo === hi);
  };
  const onInput = (which) => {
    let lo = Number(a.value), hi = Number(b.value);
    // Üks käepide lükkab teist, kui see temast üle viiakse
    if (lo > hi) { if (which === "a") hi = lo; else lo = hi; }
    state.filter[key] = [lo, hi];
    sync();
    applyFilters();
  };
  a.addEventListener("input", () => onInput("a"));
  b.addEventListener("input", () => onInput("b"));
  return sync;
}

const rangeSyncs = [];

function initFilters() {
  state.bounds = computeBounds();
  state.filter = defaultFilter();
  const rooms = (v) => roomsText(v);
  rangeSyncs.push(makeRange($("f-rooms"), {
    key: "rooms", label: "Toad", unit: "tuba", step: 1, fmt: rooms,
    text: (lo, hi) => (lo === hi ? `${rooms(lo)} tuba` : `${rooms(lo)}–${rooms(hi)} tuba`),
  }));
  rangeSyncs.push(makeRange($("f-price"), {
    key: "price", label: "Hind", unit: "€", step: PRICE_STEP, fmt: (v) => eur.format(v),
    text: (lo, hi) => `${eur.format(lo)} – ${eur.format(hi)} €`,
  }));
  rangeSyncs.push(makeRange($("f-floor"), {
    key: "floor", label: "Korrus", unit: "", step: 1, fmt: (v) => `${v}. korrus`,
    text: (lo, hi) => (lo === hi ? `${lo}` : `${lo}–${hi}`),
  }));
  const unknown = state.data.listings.filter((l) => l.floor == null).length;
  $("floor-hint").textContent = unknown
    ? `Teadmata korrusega kuulutused (${unknown}) jäävad alati nähtavale.`
    : "Teadmata korrusega kuulutused jäävad alati nähtavale.";
  $("asum").innerHTML = `<option value="">Kõik asumid</option>` +
    state.bounds.asums.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  $("not-first").addEventListener("change", (e) => { state.filter.notFirst = e.target.checked; applyFilters(); });
  $("not-last").addEventListener("change", (e) => { state.filter.notLast = e.target.checked; applyFilters(); });
  $("asum").addEventListener("change", (e) => { state.filter.asum = e.target.value; applyFilters(); });
  $("reset").addEventListener("click", () => {
    state.filter = defaultFilter(); syncFilterControls(); applyFilters();
    $("f-rooms-a").focus();
  });
  syncFilterControls();
}

function syncFilterControls() {
  rangeSyncs.forEach((s) => s());
  $("not-first").checked = state.filter.notFirst;
  $("not-last").checked = state.filter.notLast;
  $("asum").value = state.filter.asum;
}

function isDefaultFilter() {
  return !state.filter || JSON.stringify(state.filter) === JSON.stringify(defaultFilter());
}

function applyFilters() {
  renderListTable();
  renderDots();
}

function selectAsum(name) {
  if (!state.filter) return; // kuulutusi pole, filtrit pole
  state.filter.asum = state.bounds.asums.includes(name) ? name : "";
  syncFilterControls();
  applyFilters();
  const h = $("kuulutused");
  h.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
  h.focus({ preventScroll: true });
}

// --- Sisu ---

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
  state.map = map;
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  state.circles = d.subdistricts.filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lon)).map((s) => {
    const c = L.circle([s.lat, s.lon], { radius: 120 + Math.sqrt(s.n) * 60, weight: 1, fillOpacity: 0.78, className: "sub-circle" })
      .bindTooltip(`${esc(s.name)}: ${fmtPct(s.residual_median)} mudelist (${s.n} kuulutust) · klõpsa, et näha kuulutusi`)
      .on("click", () => selectAsum(s.name))
      .addTo(map);
    c.residual = s.residual_median;
    return c;
  });
  state.dotLayer = L.layerGroup().addTo(map);
  L.circleMarker(VABADUSE, { radius: 6, color: css("--muted"), weight: 2, dashArray: "3", fillOpacity: 0, interactive: true })
    .bindTooltip("Vabaduse väljak").addTo(map);
  L.circleMarker([center.lat, center.lon], { radius: 9, color: css("--ink"), weight: 3, fillOpacity: 0 })
    .bindTooltip("Andmetest leitud keskpunkt").addTo(map);
  styleCircles();
  renderDots();
}

function styleCircles() {
  const ring = css("--map-ring");
  state.circles.forEach((c) => c.setStyle({ color: ring, fillColor: state.scales.subColor(c.residual) }));
}

function renderDots() {
  if (!state.dotLayer) return;
  state.dotLayer.clearLayers();
  const ring = css("--surface");
  filtered().filter((l) => Number.isFinite(l.lat) && Number.isFinite(l.lon)).forEach((l) => {
    L.circleMarker([l.lat, l.lon], { radius: 5, color: ring, weight: 1.5, fillColor: state.scales.dotColor(l.residual), fillOpacity: 1 })
      .bindPopup(`<a href="${esc(safeUrl(l.url))}" target="_blank" rel="noopener">${esc(l.address)}</a><br>` +
        `${eur.format(l.price)} € · mudel ${eur.format(l.predicted_price)} € (${fmtPct(l.residual)})`)
      .addTo(state.dotLayer);
  });
}

function renderLegend() {
  const s = state.scales, dv = s.div;
  $("legend").innerHTML = `
    <figure class="scale">
      <figcaption>Asum: mediaanhind mudeli suhtes</figcaption>
      <span class="bar" style="background:${gradient(s.divRamp)}" aria-hidden="true"></span>
      <span class="ticks"><span>${pctTick.format(-dv)} odavam</span><span>0</span><span>kallim ${pctTick.format(dv)}</span></span>
    </figure>
    ${state.data.listings.length ? `<figure class="scale">
      <figcaption>Täpp: alahinnatud kuulutus, hind mudeli suhtes</figcaption>
      <span class="bar" style="background:${gradient(s.seqRamp)}" aria-hidden="true"></span>
      <span class="ticks"><span>${pctTick.format(UNDERVALUED)}</span><span>${pctTick.format(s.low)} või vähem</span></span>
    </figure>` : ""}
    <p class="legend-note">Paks ring = andmetest leitud keskpunkt · katkendlik ring = Vabaduse väljak ·
      klõpsa asumil, et näha selle kuulutusi</p>`;
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

const floorText = (r) => (r.floor == null ? "–" : r.floors_total != null ? `${r.floor}/${r.floors_total}` : String(r.floor));

const SUB_COLS = [
  { key: "name", label: "Asum", cell: (r) => `<button type="button" class="row-link" data-asum="${esc(r.name)}">${esc(r.name)}</button>` },
  { key: "residual_median", label: "Hind mudeli suhtes", num: true, cell: (r) => fmtPct(r.residual_median) },
  { key: "n", label: "Kuulutusi", num: true, cell: (r) => r.n },
];
const LIST_COLS = [
  { key: "address", label: "Aadress", cell: (r) => `<a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${esc(r.address)}</a>` },
  { key: "subdistrict", label: "Asum", cell: (r) => esc(r.subdistrict) },
  { key: "rooms", label: "Toad", num: true, cell: (r) => r.rooms ?? "–" },
  { key: "floor", label: "Korrus", num: true, cell: floorText },
  { key: "price", label: "Hind €", num: true, cell: (r) => eur.format(r.price) },
  { key: "predicted_price", label: "Mudel €", num: true, cell: (r) => eur.format(r.predicted_price) },
  { key: "residual", label: "Erinevus", num: true, cell: (r) => fmtPct(r.residual) },
  { key: "yield", label: "Tootlus (mudel)", num: true, cell: (r) => fmtPct(r.yield) },
];

function renderTable(id, cols, rows, sortState, onSort, rowAttr = () => "") {
  const t = $(id);
  t.querySelector("thead").innerHTML = "<tr>" + cols.map((c) => {
    const aria = sortState.key === c.key ? (sortState.dir > 0 ? "ascending" : "descending") : "none";
    return `<th class="${c.num ? "num" : ""}" aria-sort="${aria}"><button type="button" data-sort="${c.key}">${c.label}</button></th>`;
  }).join("") + "</tr>";
  t.querySelector("tbody").innerHTML = rows.length
    ? rows.map((r) => `<tr${rowAttr(r)}>` + cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.cell(r)}</td>`).join("") + "</tr>").join("")
    : `<tr><td colspan="${cols.length}" class="muted">Sobivaid kuulutusi pole.${isDefaultFilter() ? "" : " Muuda filtreid või lähtesta need."}</td></tr>`;
  t.querySelector("thead").onclick = (e) => {
    const key = e.target.closest("button")?.dataset.sort;
    if (!key) return;
    onSort(key);
    $(id).querySelector(`thead [data-sort="${key}"]`)?.focus();
  };
}

const toggle = (s, key) => ({ key, dir: s.key === key ? -s.dir : 1 });

function renderSubTable() {
  renderTable("t-sub", SUB_COLS, sortRows([...state.data.subdistricts], state.sortSub), state.sortSub,
    (key) => { state.sortSub = toggle(state.sortSub, key); renderSubTable(); },
    (r) => ` class="pick" data-asum="${esc(r.name)}"`);
}

let countT;
function renderListTable() {
  const list = filtered();
  renderTable("t-list", LIST_COLS, sortRows([...list], state.sortList), state.sortList,
    (key) => { state.sortList = toggle(state.sortList, key); renderListTable(); });
  clearTimeout(countT);
  const text = `${list.length} / ${state.data.listings.length} kuulutust`;
  countT = setTimeout(() => { $("count").textContent = text; }, $("count").textContent ? 400 : 0);
  $("reset").disabled = isDefaultFilter();
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
  state.scales = computeScales();
  renderStats();
  renderCharts();
  renderSubTable();
  if (data.listings.length) {
    initFilters();
    renderListTable();
  } else {
    $("list-filters").hidden = true;
    $("list-wrap").hidden = true;
    $("list-empty").hidden = false;
  }
  renderLegend();
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

// Heleda/tumeda teema vahetus: skaala peatused tulevad CSS-ist, seega arvuta värvid uuesti
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (!state.data) return;
  state.scales = computeScales();
  renderLegend();
  if (state.map) { styleCircles(); renderDots(); }
});

$("t-sub").querySelector("tbody").addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-asum]");
  if (row && !e.target.closest("a")) selectAsum(row.dataset.asum);
});
load();
