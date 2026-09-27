"use strict";

// Lab 8 - coordinated semantic exploration of the DKU Undergraduate Bulletin.
// All analytical values come from the committed data/lab8_* artifacts; nothing
// analytical is hard-coded here. Bulletin text is inserted with safe DOM methods
// (textContent / D3 .text()) only - never innerHTML/insertAdjacentHTML.

const DATA = "../data/";

// ten well-separated hues for the ten semantic topics (Tableau 10)
const TOPIC_COLORS = [
  "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1",
  "#76b7b2", "#edc948", "#af7aa1", "#ff9da7", "#9c755f",
];
const FADE = 0.06;
const MATRIX_FADE = 0.12;
const DIM = 0.85;

// central interaction state; one render path reads from it
const state = {
  query: "",
  topic: "all",
  section: "all",
  selected: null,
  neighborIds: [],
  matrixSel: null, // { section, topic }
};

let mapData = [];
let byId = new Map();
let neighborsData = {};
let topicNames = []; // index = cluster id
let color;
let xScale, yScale, sizeScale;
let pointSel, zoomG, mapSvg, zoomBehavior;
let matrixLookup = new Map(); // "section\u0000topic" -> {count, proportion, section_total}
let tooltip;

// --------------------------------------------------------------------------- //
// bootstrap                                                                    //
// --------------------------------------------------------------------------- //

Promise.all([
  d3.csv(DATA + "lab8_embedding_map.csv", (d) => ({
    passage_id: d.passage_id,
    chapter: d.chapter,
    section: d.section,
    subsection: d.subsection || "",
    page: +d.page,
    page_end: +(d.page_end || d.page),
    text: d.text,
    word_count: +d.word_count,
    cluster: +d.cluster,
    cluster_name: d.cluster_name,
    x: +d.x,
    y: +d.y,
  })),
  d3.csv(DATA + "lab8_section_summary.csv", (d) => ({
    section: d.section,
    passage_count: +d.passage_count,
  })),
  d3.csv(DATA + "lab8_top_terms.csv", (d) => ({ term: d.term, tfidf: +d.tfidf })),
  d3.csv(DATA + "lab8_topic_section_matrix.csv", (d) => ({
    section: d.section,
    topic: d.topic,
    count: +d.count,
    section_total: +d.section_total,
    proportion: +d.proportion,
  })),
  d3.json(DATA + "lab8_neighbors.json"),
  d3.json(DATA + "lab8_corpus_summary.json"),
])
  .then(init)
  .catch((err) => {
    const box = document.getElementById("load-error");
    box.hidden = false;
    box.textContent = "Could not load Lab 8 data: " + err.message +
      " - run 'python lab8/prepare_lab8.py' and serve the repository root over HTTP.";
    console.error(err);
  });

function init([map, sectionSummary, terms, matrix, neighbors, summary]) {
  mapData = map;
  neighborsData = neighbors;
  byId = new Map(map.map((d) => [d.passage_id, d]));
  tooltip = d3.select("#tooltip");

  // topic id -> name
  topicNames = [];
  map.forEach((d) => { topicNames[d.cluster] = d.cluster_name; });
  color = d3.scaleOrdinal().domain(d3.range(topicNames.length)).range(TOPIC_COLORS);

  matrix.forEach((row) => {
    matrixLookup.set(row.section + "\u0000" + row.topic, row);
  });

  fillCorpusMeta(summary);
  buildSectionChart(sectionSummary);
  buildTermsChart(terms);
  buildFilters();
  buildTopicLegend();
  buildMap();
  buildMatrix(matrix);
  wireControls();
  updateVisualState();
}

// --------------------------------------------------------------------------- //
// section 1 - corpus meta                                                      //
// --------------------------------------------------------------------------- //

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function fillCorpusMeta(s) {
  setText("stat-pages", s.pdf_pages.toLocaleString());
  setText("stat-raw", s.raw_passages.toLocaleString());
  setText("stat-clean", s.clean_passages.toLocaleString());
  setText("stat-avg", s.average_word_count);
  setText("stat-sections", s.formal_section_count.toLocaleString());
  setText("stat-topics", s.clustering.k);
  setText("section-count-inline", s.formal_section_count);
  setText("meta-title", s.bulletin_title);
  setText("meta-version", s.bulletin_version);
  setText("meta-accessed", s.accessed_date);
  const link = document.getElementById("meta-source");
  link.textContent = s.source;
  link.setAttribute("href", s.source);
}

// --------------------------------------------------------------------------- //
// section 2 - overview charts                                                  //
// --------------------------------------------------------------------------- //

function buildSectionChart(rows) {
  const data = rows.slice().sort((a, b) => b.passage_count - a.passage_count);
  const rowH = 18;
  const labelW = 150;
  const barMax = 150;
  const width = labelW + barMax + 42;
  const height = data.length * rowH + 8;
  const max = d3.max(data, (d) => d.passage_count);
  const x = d3.scaleLinear().domain([0, max]).range([0, barMax]);

  const svg = d3.select("#section-chart").append("svg")
    .attr("width", width).attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`);

  const g = svg.selectAll("g").data(data).join("g")
    .attr("transform", (d, i) => `translate(0,${i * rowH + 4})`);

  g.append("text").attr("class", "lab8-bar-label")
    .attr("x", labelW - 6).attr("y", rowH / 2).attr("dy", "0.32em")
    .attr("text-anchor", "end")
    .text((d) => d.section.length > 24 ? d.section.slice(0, 23) + "…" : d.section)
    .append("title").text((d) => d.section);

  g.append("rect").attr("class", "lab8-bar")
    .attr("x", labelW).attr("y", 2)
    .attr("width", (d) => Math.max(1, x(d.passage_count))).attr("height", rowH - 6);

  g.append("text").attr("class", "lab8-bar-value")
    .attr("x", (d) => labelW + Math.max(1, x(d.passage_count)) + 4)
    .attr("y", rowH / 2).attr("dy", "0.32em").text((d) => d.passage_count);
}

function buildTermsChart(terms) {
  const data = terms.slice(0, 20);
  const rowH = 20;
  const labelW = 120;
  const barMax = 150;
  const width = labelW + barMax + 50;
  const height = data.length * rowH + 8;
  const max = d3.max(data, (d) => d.tfidf);
  const x = d3.scaleLinear().domain([0, max]).range([0, barMax]);

  const svg = d3.select("#terms-chart").append("svg")
    .attr("width", "100%").attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`);

  const g = svg.selectAll("g").data(data).join("g")
    .attr("transform", (d, i) => `translate(0,${i * rowH + 4})`);

  g.append("text").attr("class", "lab8-bar-label")
    .attr("x", labelW - 6).attr("y", rowH / 2).attr("dy", "0.32em")
    .attr("text-anchor", "end").text((d) => d.term);

  g.append("rect").attr("class", "lab8-bar-alt")
    .attr("x", labelW).attr("y", 2)
    .attr("width", (d) => Math.max(1, x(d.tfidf))).attr("height", rowH - 6);

  g.append("text").attr("class", "lab8-bar-value")
    .attr("x", (d) => labelW + Math.max(1, x(d.tfidf)) + 4)
    .attr("y", rowH / 2).attr("dy", "0.32em").text((d) => d.tfidf.toFixed(3));
}

// --------------------------------------------------------------------------- //
// filters + legend                                                            //
// --------------------------------------------------------------------------- //

function buildFilters() {
  const topicSelect = d3.select("#topic-filter");
  topicNames.forEach((name) => {
    topicSelect.append("option").attr("value", name).text(name);
  });

  const sections = Array.from(new Set(mapData.map((d) => d.section)))
    .sort((a, b) => a.localeCompare(b));
  const sectionSelect = d3.select("#section-filter");
  sections.forEach((s) => {
    sectionSelect.append("option").attr("value", s).text(s);
  });
}

function buildTopicLegend() {
  const legend = d3.select("#topic-legend");
  const counts = d3.rollup(mapData, (v) => v.length, (d) => d.cluster);
  topicNames.forEach((name, cluster) => {
    const item = legend.append("button")
      .attr("type", "button").attr("class", "lab8-swatch")
      .attr("title", "Filter to this topic");
    item.append("span").attr("class", "lab8-swatch-dot")
      .style("background", color(cluster));
    item.append("span").text(`${name} (${counts.get(cluster) || 0})`);
    item.on("click", () => {
      state.topic = state.topic === name ? "all" : name;
      document.getElementById("topic-filter").value = state.topic;
      state.selected = null; state.neighborIds = [];
      renderDetailEmpty();
      updateVisualState();
    });
  });
}

// --------------------------------------------------------------------------- //
// section 3 - semantic map                                                     //
// --------------------------------------------------------------------------- //

const MAP_W = 900;
const MAP_H = 620;
const MAP_PAD = 26;

function buildMap() {
  mapSvg = d3.select("#semantic-map")
    .attr("viewBox", `0 0 ${MAP_W} ${MAP_H}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("height", MAP_H + "px");

  xScale = d3.scaleLinear()
    .domain(d3.extent(mapData, (d) => d.x)).range([MAP_PAD, MAP_W - MAP_PAD]);
  yScale = d3.scaleLinear()
    .domain(d3.extent(mapData, (d) => d.y)).range([MAP_H - MAP_PAD, MAP_PAD]);
  sizeScale = d3.scaleSqrt()
    .domain(d3.extent(mapData, (d) => d.word_count)).range([2.5, 9]);

  zoomG = mapSvg.append("g");

  pointSel = zoomG.selectAll("circle").data(mapData, (d) => d.passage_id)
    .join("circle")
    .attr("class", "lab8-point")
    .attr("cx", (d) => xScale(d.x))
    .attr("cy", (d) => yScale(d.y))
    .attr("r", (d) => sizeScale(d.word_count))
    .attr("fill", (d) => color(d.cluster))
    .on("click", (event, d) => { event.stopPropagation(); selectPassage(d.passage_id); })
    .on("mousemove", (event, d) => showTooltip(event, [
      { strong: true, text: d.section },
      { text: `${d.cluster_name} · ${pageShort(d)} · ${d.word_count} words` },
    ]))
    .on("mouseleave", hideTooltip);

  zoomBehavior = d3.zoom().scaleExtent([0.5, 12])
    .on("start", () => mapSvg.classed("is-panning", true))
    .on("zoom", (event) => zoomG.attr("transform", event.transform))
    .on("end", () => mapSvg.classed("is-panning", false));
  mapSvg.call(zoomBehavior);
  mapSvg.on("click", () => { clearSelection(); updateVisualState(); });
}

function passesFilter(d) {
  const q = state.query;
  const matchQuery = q === "" ||
    d.text.toLowerCase().includes(q) ||
    d.section.toLowerCase().includes(q) ||
    d.subsection.toLowerCase().includes(q);
  const matchTopic = state.topic === "all" || d.cluster_name === state.topic;
  const matchSection = state.section === "all" || d.section === state.section;
  return matchQuery && matchTopic && matchSection;
}

// the single deterministic render path for all coordinated emphasis
function updateVisualState() {
  const nbrSet = new Set(state.neighborIds);
  const ms = state.matrixSel;
  let matchCount = 0;

  pointSel.each(function (d) {
    const isSel = d.passage_id === state.selected;
    const isNbr = nbrSet.has(d.passage_id);
    const isMatrix = !!ms && d.section === ms.section && d.cluster_name === ms.topic;
    const passes = passesFilter(d);
    if (passes) matchCount += 1;

    let opacity;
    if (isSel || isNbr) opacity = 1;
    else if (!passes) opacity = FADE;
    else if (ms) opacity = isMatrix ? 1 : MATRIX_FADE;
    else opacity = DIM;

    const node = d3.select(this);
    node.attr("opacity", opacity)
      .attr("r", isSel ? sizeScale(d.word_count) + 3 : sizeScale(d.word_count))
      .classed("is-selected", isSel)
      .classed("is-neighbor", isNbr && !isSel)
      .classed("is-matrix", isMatrix && !isSel && !isNbr);
  });

  // draw emphasized points on top
  pointSel.filter((d) => state.matrixSel &&
    d.section === state.matrixSel.section && d.cluster_name === state.matrixSel.topic).raise();
  pointSel.filter((d) => state.neighborIds.includes(d.passage_id)).raise();
  pointSel.filter((d) => d.passage_id === state.selected).raise();

  updateMapStatus(matchCount);
  updateMatrixHighlight();
}

function updateMapStatus(matchCount) {
  const parts = [];
  if (state.query) parts.push(`search "${state.query}"`);
  if (state.topic !== "all") parts.push(`topic ${state.topic}`);
  if (state.section !== "all") parts.push(`section ${state.section}`);
  const filterText = parts.length ? " matching " + parts.join(" AND ") : "";
  const el = document.getElementById("map-status");
  el.replaceChildren();
  const strong = document.createElement("strong");
  strong.textContent = matchCount.toLocaleString();
  el.appendChild(strong);
  el.appendChild(document.createTextNode(
    ` of ${mapData.length.toLocaleString()} passages${filterText}.` +
    (state.selected ? " Selected passage highlighted with its 5 neighbours." : "")));
}

// --------------------------------------------------------------------------- //
// selection + detail panel                                                    //
// --------------------------------------------------------------------------- //

function selectPassage(id) {
  const d = byId.get(id);
  if (!d) return;
  state.selected = id;
  state.neighborIds = (neighborsData[id] || []).map((n) => n.passage_id);
  renderDetail(d);
  updateVisualState();
}

function clearSelection() {
  state.selected = null;
  state.neighborIds = [];
  renderDetailEmpty();
}

function renderDetailEmpty() {
  const body = document.getElementById("detail-body");
  body.replaceChildren();
  const p = document.createElement("p");
  p.className = "lab8-detail-empty";
  p.textContent = "Click a point on the map (or a neighbour below) to inspect a passage.";
  body.appendChild(p);
  document.getElementById("neighbors-block").hidden = true;
  document.getElementById("neighbor-list").replaceChildren();
}

function metaRow(dl, term, value) {
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = value;
  dl.appendChild(dt);
  dl.appendChild(dd);
}

function renderDetail(d) {
  const body = document.getElementById("detail-body");
  body.replaceChildren();

  const badge = document.createElement("span");
  badge.className = "lab8-detail-topic";
  badge.style.background = color(d.cluster);
  badge.textContent = d.cluster_name;
  body.appendChild(badge);

  const dl = document.createElement("dl");
  dl.className = "lab8-detail-meta";
  metaRow(dl, "Passage", d.passage_id);
  metaRow(dl, "Chapter", d.chapter);
  metaRow(dl, "Section", d.section);
  metaRow(dl, "Subsection", d.subsection || "—");
  const spansPages = d.page_end && d.page_end > d.page;
  metaRow(dl, spansPages ? "PDF pages" : "PDF page",
    spansPages ? `${d.page}–${d.page_end}` : String(d.page));
  metaRow(dl, "Word count", String(d.word_count));
  body.appendChild(dl);

  const text = document.createElement("p");
  text.className = "lab8-detail-text";
  text.textContent = d.text;
  body.appendChild(text);

  renderNeighbors(d);
}

function renderNeighbors(d) {
  const block = document.getElementById("neighbors-block");
  const list = document.getElementById("neighbor-list");
  list.replaceChildren();
  const neighbors = neighborsData[d.passage_id] || [];
  if (!neighbors.length) { block.hidden = true; return; }
  block.hidden = false;

  neighbors.forEach((n) => {
    const nd = byId.get(n.passage_id);
    if (!nd) return;
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "lab8-neighbor";

    const head = document.createElement("div");
    head.className = "lab8-neighbor-head";
    const where = document.createElement("span");
    where.textContent = `${nd.section} · ${pageShort(nd)}`;
    const sim = document.createElement("span");
    sim.className = "lab8-neighbor-sim";
    sim.textContent = "cos " + n.similarity.toFixed(3);
    head.appendChild(where);
    head.appendChild(sim);

    const excerpt = document.createElement("div");
    excerpt.className = "lab8-neighbor-text";
    excerpt.textContent = nd.text.length > 150 ? nd.text.slice(0, 149) + "…" : nd.text;

    btn.appendChild(head);
    btn.appendChild(excerpt);
    btn.addEventListener("click", () => selectPassage(nd.passage_id));
    li.appendChild(btn);
    list.appendChild(li);
  });
}

// --------------------------------------------------------------------------- //
// section 4 - topic x section matrix                                           //
// --------------------------------------------------------------------------- //

const CELL_W = 76;
const CELL_H = 21;
const MATRIX_LABEL_W = 210;
const MATRIX_HEAD_H = 96;

let matrixColor, matrixSections, matrixCellSel, matrixRowLabelSel;

function buildMatrix(rows) {
  matrixSections = Array.from(new Set(rows.map((r) => r.section)))
    .sort((a, b) => a.localeCompare(b));
  const maxCount = d3.max(rows, (r) => r.count) || 1;
  matrixColor = d3.scaleSequential(d3.interpolateBlues).domain([0, maxCount]);

  const totalW = MATRIX_LABEL_W + topicNames.length * CELL_W + 4;

  // header (topic labels) - stays fixed above the scroll body
  const head = d3.select("#matrix-header")
    .attr("width", totalW).attr("height", MATRIX_HEAD_H)
    .attr("viewBox", `0 0 ${totalW} ${MATRIX_HEAD_H}`);
  head.append("text").attr("x", 8).attr("y", MATRIX_HEAD_H - 10)
    .attr("class", "lab8-matrix-collabel").style("font-weight", "700").text("Section \\ Topic");
  topicNames.forEach((name, i) => {
    const cx = MATRIX_LABEL_W + i * CELL_W + CELL_W / 2;
    head.append("g").attr("transform", `translate(${cx},${MATRIX_HEAD_H - 8}) rotate(-40)`)
      .append("text").attr("class", "lab8-matrix-collabel")
      .attr("fill", color(i)).style("font-weight", "700")
      .text(shorten(name, 22)).append("title").text(name);
  });

  // body
  const bodyH = matrixSections.length * CELL_H + 4;
  const body = d3.select("#matrix-body")
    .attr("width", totalW).attr("height", bodyH)
    .attr("viewBox", `0 0 ${totalW} ${bodyH}`);

  const rowG = body.selectAll("g.row").data(matrixSections).join("g")
    .attr("class", "row").attr("transform", (d, i) => `translate(0,${i * CELL_H + 2})`);

  matrixRowLabelSel = rowG.append("text").attr("class", "lab8-matrix-rowlabel")
    .attr("x", MATRIX_LABEL_W - 6).attr("y", CELL_H / 2).attr("dy", "0.32em")
    .attr("text-anchor", "end").text((d) => shorten(d, 30));
  matrixRowLabelSel.append("title").text((d) => d);

  const cells = [];
  matrixSections.forEach((sec) => {
    topicNames.forEach((topic, ti) => {
      cells.push({ section: sec, topic, ti });
    });
  });

  matrixCellSel = body.selectAll("rect.lab8-cell").data(cells).join("rect")
    .attr("class", "lab8-cell")
    .attr("x", (d) => MATRIX_LABEL_W + d.ti * CELL_W)
    .attr("y", (d) => matrixSections.indexOf(d.section) * CELL_H + 2)
    .attr("width", CELL_W - 1).attr("height", CELL_H - 1)
    .attr("fill", (d) => {
      const rec = matrixLookup.get(d.section + "\u0000" + d.topic);
      return rec && rec.count > 0 ? matrixColor(rec.count) : "#f2f5f8";
    })
    .on("mousemove", (event, d) => {
      const rec = matrixLookup.get(d.section + "\u0000" + d.topic) ||
        { count: 0, proportion: 0, section_total: 0 };
      showTooltip(event, [
        { strong: true, text: d.section },
        { text: d.topic },
        { text: `${rec.count} passages · ${(rec.proportion * 100).toFixed(1)}% of section (${rec.section_total} total)` },
      ]);
    })
    .on("mouseleave", hideTooltip)
    .on("click", (event, d) => {
      event.stopPropagation();
      const same = state.matrixSel &&
        state.matrixSel.section === d.section && state.matrixSel.topic === d.topic;
      state.matrixSel = same ? null : { section: d.section, topic: d.topic };
      updateVisualState();
    });

  // matrix legend gradient
  const grad = document.getElementById("matrix-gradient");
  grad.style.background =
    `linear-gradient(to right, ${matrixColor(0)}, ${matrixColor(maxCount / 2)}, ${matrixColor(maxCount)})`;
  setText("matrix-max", String(maxCount));

  // keep header aligned with horizontal scroll of the body
  const scroller = document.querySelector(".lab8-matrix-scroll");
  const headWrap = document.querySelector(".lab8-matrix-head");
  scroller.addEventListener("scroll", () => { headWrap.scrollLeft = scroller.scrollLeft; });
}

function updateMatrixHighlight() {
  const ms = state.matrixSel;
  const sel = state.selected ? byId.get(state.selected) : null;

  matrixCellSel
    .classed("is-active", (d) => !!ms && d.section === ms.section && d.topic === ms.topic)
    .classed("is-point", (d) => !!sel && d.section === sel.section && d.topic === sel.cluster_name);

  matrixRowLabelSel.classed("is-active", (d) =>
    (!!ms && d === ms.section) || (!!sel && d === sel.section));

  const status = document.getElementById("matrix-status");
  if (ms) {
    const rec = matrixLookup.get(ms.section + "\u0000" + ms.topic) || { count: 0 };
    status.textContent =
      `Matrix selection: ${ms.section} × ${ms.topic} — ${rec.count} passages highlighted on the map.`;
  } else if (sel) {
    status.textContent =
      `Selected point sits in ${sel.section} × ${sel.cluster_name} (outlined in the matrix).`;
  } else {
    status.textContent = "No matrix cell selected.";
  }
}

// --------------------------------------------------------------------------- //
// controls                                                                     //
// --------------------------------------------------------------------------- //

function wireControls() {
  document.getElementById("search").addEventListener("input", function () {
    state.query = this.value.toLowerCase().trim();
    updateVisualState();
  });
  document.getElementById("topic-filter").addEventListener("change", function () {
    state.topic = this.value;
    updateVisualState();
  });
  document.getElementById("section-filter").addEventListener("change", function () {
    state.section = this.value;
    updateVisualState();
  });
  document.getElementById("reset-map").addEventListener("click", resetAll);
  document.getElementById("clear-matrix").addEventListener("click", () => {
    state.matrixSel = null;
    updateVisualState();
  });
}

function resetAll() {
  state.query = "";
  state.topic = "all";
  state.section = "all";
  state.matrixSel = null;
  clearSelection();
  document.getElementById("search").value = "";
  document.getElementById("topic-filter").value = "all";
  document.getElementById("section-filter").value = "all";
  mapSvg.transition().duration(300).call(zoomBehavior.transform, d3.zoomIdentity);
  updateVisualState();
}

// --------------------------------------------------------------------------- //
// helpers                                                                      //
// --------------------------------------------------------------------------- //

function shorten(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function pageShort(d) {
  return d.page_end && d.page_end > d.page ? `p${d.page}–${d.page_end}` : `p${d.page}`;
}

// tooltip content is built from DOM nodes with textContent only - no innerHTML
function showTooltip(event, lines) {
  const node = tooltip.node();
  node.replaceChildren();
  lines.forEach((line, i) => {
    if (i > 0) node.appendChild(document.createElement("br"));
    if (line.strong) {
      const el = document.createElement("strong");
      el.textContent = line.text;
      node.appendChild(el);
    } else {
      node.appendChild(document.createTextNode(line.text));
    }
  });
  tooltip.style("display", "block").attr("aria-hidden", "false")
    .style("left", (event.pageX + 14) + "px")
    .style("top", (event.pageY + 14) + "px");
}

function hideTooltip() {
  tooltip.style("display", "none").attr("aria-hidden", "true");
}
