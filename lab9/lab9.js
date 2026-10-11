"use strict";

// Local, committed artifacts only. GDP is joined to geography exclusively by ISO-3.
const DATA = "../data/";
const MAP_HEIGHT = 510;
const NO_DATA_COLOR = "#d8dce0";
const state = { hoverIso: null, lockedIso: null };
let rows = [];
let features = [];
let gdpByIso = new Map();
let color;
let choroPaths;
let cartPaths;
let zoomBehavior;
let choroSvg;
let redrawTimer;

if (typeof window !== "undefined") {
  Promise.all([
    d3.csv(DATA + "lab9_gdp_2025_top50.csv", (d) => ({
    iso3: d.iso3,
    country: d.country,
    gdp: +d.gdp_2025_billion_usd,
    rank: +d.rank,
  })),
    d3.json(DATA + "lab9_world.geojson"),
  ]).then(init).catch(showLoadError);
}

function init([gdpRows, world]) {
  rows = gdpRows.slice().sort((a, b) => a.rank - b.rank);
  features = world.features;
  gdpByIso = new Map(rows.map((d) => [d.iso3, d]));
  color = d3.scaleSequentialLog(d3.interpolateYlGnBu)
    .domain(d3.extent(rows, (d) => d.gdp));
  fillSummary();
  buildCountrySelect();
  buildLegend();
  wireControls();
  renderMaps();
  const resizeObserver = new ResizeObserver(() => {
    window.clearTimeout(redrawTimer);
    redrawTimer = window.setTimeout(renderMaps, 100);
  });
  resizeObserver.observe(document.querySelector(".lab9-map-card figure"));
}

function showLoadError(error) {
  const box = document.getElementById("load-error");
  box.hidden = false;
  box.textContent = "Could not load Lab 9 data: " + error.message +
    ". Serve the repository root over HTTP after running lab9/prepare_lab9.py.";
  console.error(error);
}

function fillSummary() {
  const high = rows[0];
  const low = rows[rows.length - 1];
  setText("stat-count", rows.length.toLocaleString());
  setText("stat-high", `${high.country} (${formatGdp(high.gdp)})`);
  setText("stat-low", `${low.country} (${formatGdp(low.gdp)})`);
}

function buildCountrySelect() {
  const select = d3.select("#country-select");
  select.selectAll("option.country-option").data(rows).join("option")
    .attr("class", "country-option")
    .attr("value", (d) => d.iso3)
    .text((d) => `${d.rank}. ${d.country}`);
}

function buildLegend() {
  const legend = d3.select("#choropleth-legend");
  const rampWidth = 260;
  const ramp = legend.append("svg").attr("class", "legend-gradient")
    .attr("viewBox", `0 0 ${rampWidth} 14`).attr("preserveAspectRatio", "none");
  ramp.selectAll("rect").data(d3.range(rampWidth)).join("rect")
    .attr("x", (d) => d).attr("width", 1).attr("height", 14)
    .attr("fill", (d) => color(Math.exp(Math.log(rows[rows.length - 1].gdp) +
      d / (rampWidth - 1) * (Math.log(rows[0].gdp) - Math.log(rows[rows.length - 1].gdp)))));
  const ticks = logTicks(rows[rows.length - 1].gdp, rows[0].gdp);
  legend.append("div").attr("class", "legend-ticks").selectAll("span").data(ticks).join("span")
    .text((d) => formatTrillions(d));
  const noData = legend.append("div").attr("class", "legend-no-data");
  noData.append("span").attr("class", "legend-swatch");
  noData.append("span").text("No data / outside provided top 50");
}

function logTicks(min, max) {
  const candidates = [300, 1000, 3000, 10000, 30000];
  const ticks = candidates.filter((d) => d >= min * 0.9 && d <= max * 1.1);
  return ticks.length >= 3 ? ticks : d3.ticks(Math.log10(min), Math.log10(max), 5).map((d) => 10 ** d);
}

function renderMaps() {
  if (!features.length) return;
  const choroWidth = measuredWidth("choropleth-map");
  const cartWidth = measuredWidth("cartogram-map");
  renderChoropleth(choroWidth, MAP_HEIGHT);
  renderCartogram(cartWidth, MAP_HEIGHT);
  updateVisualState();
}

function measuredWidth(id) {
  const width = document.getElementById(id).parentElement.getBoundingClientRect().width;
  return Math.max(300, Math.round(width || 760));
}

function projectionAndPath(width, height) {
  const projection = d3.geoEqualEarth().fitExtent([[12, 12], [width - 12, height - 12]], {
    type: "FeatureCollection", features,
  });
  return { projection, path: d3.geoPath().projection(projection) };
}

function renderChoropleth(width, height) {
  choroSvg = d3.select("#choropleth-map").attr("viewBox", `0 0 ${width} ${height}`);
  choroSvg.selectAll("*").remove();
  choroSvg.append("title").attr("id", "choropleth-title").text("World choropleth of 2025 nominal GDP");
  choroSvg.append("desc").attr("id", "choropleth-desc").text("GDP data is coloured on actual country boundaries. Countries outside the supplied top 50 use a separate neutral no-data colour.");
  const { path } = projectionAndPath(width, height);
  const mapGroup = choroSvg.append("g").attr("class", "choropleth-zoom-group");
  choroPaths = mapGroup.selectAll("path").data(features).join("path")
    .attr("class", (d) => "country-path" + (gdpByIso.has(d.properties.iso3) ? " has-data" : " no-data"))
    .attr("d", path)
    .attr("fill", (d) => gdpByIso.has(d.properties.iso3) ? color(gdpByIso.get(d.properties.iso3).gdp) : NO_DATA_COLOR)
    .attr("tabindex", (d) => gdpByIso.has(d.properties.iso3) ? 0 : null)
    .attr("aria-label", (d) => ariaLabel(d.properties.iso3, d.properties.name))
    .on("pointerenter", function(event, d) { activateHover(event, d.properties.iso3, d.properties.name); })
    .on("pointermove", moveTooltip)
    .on("pointerleave", clearHover)
    .on("focus", function(event, d) { activateHover(event, d.properties.iso3, d.properties.name); })
    .on("blur", clearHover)
    .on("click", function(event, d) { toggleLock(d.properties.iso3); });
  zoomBehavior = d3.zoom().scaleExtent([1, 8]).on("zoom", (event) => mapGroup.attr("transform", event.transform));
  choroSvg.call(zoomBehavior);
}

function renderCartogram(width, height) {
  const svg = d3.select("#cartogram-map").attr("viewBox", `0 0 ${width} ${height}`);
  svg.selectAll("*").remove();
  svg.append("title").attr("id", "cartogram-title").text("Non-contiguous world cartogram of 2025 nominal GDP");
  svg.append("desc").attr("id", "cartogram-desc").text("Each top-50 economy is a scaled projected country silhouette whose displayed area is proportional to GDP. Faint outlines preserve geographic context.");
  const { path } = projectionAndPath(width, height);
  svg.append("g").selectAll("path").data(features).join("path").attr("class", "cart-background").attr("d", path);
  const totalGdp = d3.sum(rows, (d) => d.gdp);
  const areaBudget = width * height * 0.30;
  const gdpFeatures = features.filter((d) => gdpByIso.has(d.properties.iso3));
  cartPaths = svg.append("g").selectAll("path").data(gdpFeatures).join("path")
    .attr("class", "cartogram-country")
    .attr("d", path)
    .attr("transform", (feature) => {
      const baseArea = path.area(feature);
      const datum = gdpByIso.get(feature.properties.iso3);
      const scaleFactor = cartogramScale(baseArea, datum.gdp, totalGdp, areaBudget);
      const [cx, cy] = path.centroid(feature);
      return `translate(${cx},${cy}) scale(${scaleFactor}) translate(${-cx},${-cy})`;
    })
    .attr("tabindex", 0)
    .attr("aria-label", (d) => ariaLabel(d.properties.iso3, d.properties.name))
    .on("pointerenter", function(event, d) { activateHover(event, d.properties.iso3, d.properties.name); })
    .on("pointermove", moveTooltip)
    .on("pointerleave", clearHover)
    .on("focus", function(event, d) { activateHover(event, d.properties.iso3, d.properties.name); })
    .on("blur", clearHover)
    .on("click", function(event, d) { toggleLock(d.properties.iso3); });
}

// The central cartogram invariant: baseArea * scaleFactor^2 = targetArea.
function cartogramScale(baseArea, gdp, totalGdp, areaBudget) {
  if (!(baseArea > 0) || !(gdp > 0) || !(totalGdp > 0) || !(areaBudget > 0)) {
    throw new Error("Cartogram inputs must be positive");
  }
  const targetArea = areaBudget * gdp / totalGdp;
  const scaleFactor = Math.sqrt(targetArea / baseArea);
  if (!Number.isFinite(scaleFactor)) throw new Error("Cartogram scale is not finite");
  return scaleFactor;
}

function wireControls() {
  document.getElementById("country-select").addEventListener("change", (event) => {
    state.lockedIso = event.target.value || null;
    updateVisualState();
  });
  document.getElementById("clear-selection").addEventListener("click", () => {
    state.hoverIso = null;
    state.lockedIso = null;
    document.getElementById("country-select").value = "";
    hideTooltip();
    updateVisualState();
  });
  document.getElementById("reset-map").addEventListener("click", () => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const target = reduced ? choroSvg : choroSvg.transition().duration(300);
    target.call(zoomBehavior.transform, d3.zoomIdentity);
  });
}

function activateHover(event, iso3, name) {
  state.hoverIso = iso3;
  showTooltip(event, iso3, name);
  updateVisualState();
}

function clearHover() {
  state.hoverIso = null;
  hideTooltip();
  updateVisualState();
}

function toggleLock(iso3) {
  state.lockedIso = state.lockedIso === iso3 ? null : iso3;
  if (gdpByIso.has(iso3)) document.getElementById("country-select").value = state.lockedIso || "";
  updateVisualState();
}

function updateVisualState() {
  const active = state.hoverIso || state.lockedIso;
  if (choroPaths) choroPaths.classed("is-active", (d) => d.properties.iso3 === active)
    .classed("is-dim", (d) => Boolean(active && d.properties.iso3 !== active));
  if (cartPaths) cartPaths.classed("is-active", (d) => d.properties.iso3 === active)
    .classed("is-dim", (d) => Boolean(active && d.properties.iso3 !== active));
  const activeData = gdpByIso.get(active);
  setText("selection-status", active ? (activeData ?
    `${activeData.country} is highlighted in both views. ${formatGdp(activeData.gdp)}, GDP rank ${activeData.rank}.` :
    `${featureName(active)} is outside the provided top-50 GDP dataset.`) :
    "Hover, focus, select, or click an economy to highlight it in both views.");
}

function showTooltip(event, iso3, name) {
  const tooltip = document.getElementById("tooltip");
  const datum = gdpByIso.get(iso3);
  tooltip.replaceChildren();
  const title = document.createElement("div");
  title.className = "tip-name";
  title.textContent = datum ? datum.country : name;
  tooltip.appendChild(title);
  const detail = document.createElement("div");
  detail.textContent = datum ? `2025 nominal GDP: ${formatGdp(datum.gdp)}; GDP rank: ${datum.rank}` : "Not in provided top-50 GDP dataset";
  tooltip.appendChild(detail);
  tooltip.setAttribute("aria-hidden", "false");
  positionTooltip(event);
}

function moveTooltip(event) { positionTooltip(event); }
function positionTooltip(event) {
  const tooltip = document.getElementById("tooltip");
  const x = Math.min((event.clientX || 20) + 14, window.innerWidth - 275);
  const y = Math.min((event.clientY || 20) + 14, window.innerHeight - 80);
  tooltip.style.left = `${Math.max(8, x)}px`;
  tooltip.style.top = `${Math.max(8, y)}px`;
}
function hideTooltip() { document.getElementById("tooltip").setAttribute("aria-hidden", "true"); }
function ariaLabel(iso3, fallbackName) { const datum = gdpByIso.get(iso3); return datum ? `${datum.country}, ${formatGdp(datum.gdp)}, rank ${datum.rank}` : `${fallbackName}, not in provided top-50 GDP dataset`; }
function featureName(iso3) { const feature = features.find((d) => d.properties.iso3 === iso3); return feature ? feature.properties.name : iso3; }
function formatGdp(value) { return `$${d3.format(",.1f")(value)} billion`; }
function formatTrillions(value) { return value >= 1000 ? `$${d3.format("~g")(value / 1000)}T` : `$${d3.format("~g")(value)}B`; }
function setText(id, value) { document.getElementById(id).textContent = value; }

// Exported for the small Node proportional-area unit test and browser inspection.
if (typeof window !== "undefined") window.cartogramScale = cartogramScale;
if (typeof module !== "undefined") module.exports = { cartogramScale };
