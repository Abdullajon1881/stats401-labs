"use strict";

const DATA_PATH = "../data/critique_electricity_world_2010_2025.csv";
const colors = new Map([
  ["Coal", "#59645f"],
  ["Oil", "#b96a5d"],
  ["Gas", "#8e67a8"],
  ["Nuclear", "#d0a52d"],
  ["Hydropower", "#2e77b8"],
  ["Wind", "#4b92a7"],
  ["Solar", "#e5773f"],
  ["Bioenergy", "#68a45d"],
  ["Other renewables", "#8c9e55"],
]);

const formatTwh = d3.format(",.0f");
const formatShare = d3.format(".1f");
const state = {
  data: [],
  years: [],
  sources: [],
  bySource: new Map(),
  byYear: new Map(),
  selectedYear: null,
  hoverSource: null,
  lockedSource: null,
  shareMax: 0,
};

const dashboard = d3.select(".dashboard");
const slider = d3.select("#year-slider");
const tooltip = d3.select("#tooltip");

function activeSource() {
  return state.lockedSource || state.hoverSource;
}

function sourceRecord(source, year = state.selectedYear) {
  return state.bySource.get(source).find((row) => row.year === year);
}

function setTooltip(row, event) {
  document.querySelector("#tooltip-source").textContent = row.source;
  document.querySelector("#tooltip-year").textContent = `Year: ${row.year}`;
  document.querySelector("#tooltip-generation").textContent = `Generation: ${formatTwh(row.generation_twh)} TWh`;
  document.querySelector("#tooltip-share").textContent = `Share: ${formatShare(row.share_pct)}%`;
  tooltip.attr("hidden", null);
  if (event) moveTooltip(event);
}

function moveTooltip(event) {
  const box = document.querySelector("#tooltip").getBoundingClientRect();
  const pad = 14;
  const left = Math.min(event.clientX + pad, window.innerWidth - box.width - pad);
  const top = Math.min(event.clientY + pad, window.innerHeight - box.height - pad);
  tooltip.style("left", `${Math.max(pad, left)}px`).style("top", `${Math.max(pad, top)}px`);
}

function hideTooltip() {
  tooltip.attr("hidden", true);
}

function setHover(source) {
  state.hoverSource = source;
  updateHighlight();
}

function toggleLock(source) {
  state.lockedSource = state.lockedSource === source ? null : source;
  d3.select("#clear-highlight").property("disabled", !state.lockedSource);
  updateHighlight();
}

function updateHighlight() {
  const active = activeSource();
  dashboard.classed("has-highlight", Boolean(active));
  d3.selectAll(".source-panel, .bar-row")
    .classed("is-active", function () {
      return this.dataset.source === active;
    });
}

function addSourceInteractions(selection, getRow) {
  selection
    .on("pointerenter", function (event, datum) {
      const source = this.dataset.source;
      setHover(source);
      setTooltip(getRow(datum, source), event);
    })
    .on("pointermove", (event) => moveTooltip(event))
    .on("pointerleave", () => {
      setHover(null);
      hideTooltip();
    })
    .on("focus", function (event, datum) {
      const source = this.dataset.source;
      setHover(source);
      setTooltip(getRow(datum, source));
    })
    .on("blur", () => {
      setHover(null);
      hideTooltip();
    })
    .on("click", function () {
      toggleLock(this.dataset.source);
    })
    .on("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleLock(this.dataset.source);
      }
    });
}

function renderSmallMultiples() {
  const container = d3.select("#small-multiples");
  container.selectAll("*").remove();

  const latestYear = d3.max(state.years);
  const orderedSources = [...state.sources].sort(
    (a, b) => sourceRecord(b, latestYear).share_pct - sourceRecord(a, latestYear).share_pct,
  );

  const width = 250;
  const height = 132;
  const margin = { top: 29, right: 9, bottom: 19, left: 29 };
  const x = d3.scaleLinear()
    .domain(d3.extent(state.years))
    .range([margin.left, width - margin.right]);
  const y = d3.scaleLinear()
    .domain([0, state.shareMax])
    .range([height - margin.bottom, margin.top]);
  const line = d3.line()
    .x((d) => x(d.year))
    .y((d) => y(d.share_pct));

  orderedSources.forEach((source) => {
    const series = state.bySource.get(source);
    const panel = container.append("div")
      .attr("class", "source-panel")
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("aria-label", `${source}. Focus or click to coordinate this source across both views.`)
      .attr("data-source", source)
      .style("--source-color", colors.get(source));

    const svg = panel.append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("role", "img")
      .attr("aria-labelledby", `panel-title-${slug(source)} panel-desc-${slug(source)}`);
    svg.append("title").attr("id", `panel-title-${slug(source)}`).text(`${source} share of global electricity generation`);
    svg.append("desc").attr("id", `panel-desc-${slug(source)}`).text(`Line chart from 2010 to 2025 using the common zero to ${state.shareMax} percent scale.`);

    svg.append("text").attr("class", "panel-title").attr("x", margin.left).attr("y", 12).text(source);
    svg.append("text").attr("class", "panel-value").attr("x", width - margin.right).attr("y", 12).attr("text-anchor", "end");

    svg.selectAll(".grid-line")
      .data([0, state.shareMax / 2, state.shareMax])
      .join("line")
      .attr("class", "grid-line")
      .attr("x1", margin.left)
      .attr("x2", width - margin.right)
      .attr("y1", (d) => y(d))
      .attr("y2", (d) => y(d));

    svg.append("g")
      .attr("class", "panel-axis")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).tickValues([0, state.shareMax]).tickFormat((d) => `${d}%`).tickSize(0).tickPadding(4));
    svg.append("g")
      .attr("class", "panel-axis")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).tickValues(d3.extent(state.years)).tickFormat(d3.format("d")).tickSize(0).tickPadding(5));

    svg.append("path").datum(series).attr("class", "source-line").attr("d", line);
    svg.append("line").attr("class", "selection-guide");
    svg.append("circle").attr("class", "selected-dot").attr("r", 4.2);

    const capture = svg.append("rect")
      .attr("class", "hover-capture")
      .attr("x", margin.left)
      .attr("y", margin.top)
      .attr("width", width - margin.left - margin.right)
      .attr("height", height - margin.top - margin.bottom)
      .on("pointerenter", () => setHover(source))
      .on("pointermove", function (event) {
        const [pointerX] = d3.pointer(event, this);
        const year = Math.max(state.years[0], Math.min(state.years.at(-1), Math.round(x.invert(pointerX + margin.left))));
        setTooltip(sourceRecord(source, year), event);
      })
      .on("pointerleave", () => {
        setHover(null);
        hideTooltip();
      })
      .on("click", (event) => {
        event.stopPropagation();
        toggleLock(source);
      });

    capture.raise();
    addSourceInteractions(panel, () => sourceRecord(source));
  });

  updateSmallMultipleSelection();
}

function updateSmallMultipleSelection() {
  d3.selectAll(".source-panel").each(function () {
    const source = this.dataset.source;
    const row = sourceRecord(source);
    const svg = d3.select(this).select("svg");
    const width = 250;
    const height = 132;
    const margin = { top: 29, right: 9, bottom: 19, left: 29 };
    const x = d3.scaleLinear().domain(d3.extent(state.years)).range([margin.left, width - margin.right]);
    const y = d3.scaleLinear().domain([0, state.shareMax]).range([height - margin.bottom, margin.top]);
    svg.select(".panel-value").text(`${formatShare(row.share_pct)}%`);
    svg.select(".selection-guide")
      .attr("x1", x(row.year)).attr("x2", x(row.year))
      .attr("y1", margin.top).attr("y2", height - margin.bottom);
    svg.select(".selected-dot").attr("cx", x(row.year)).attr("cy", y(row.share_pct));
  });
}

function renderBars(animate = true) {
  const host = document.querySelector("#bar-chart");
  const width = Math.max(320, Math.floor(host.clientWidth || 440));
  const rowHeight = 43;
  const height = state.sources.length * rowHeight + 48;
  const margin = { top: 14, right: width < 480 ? 66 : 92, bottom: 30, left: width < 480 ? 108 : 126 };
  const rows = [...state.byYear.get(state.selectedYear)].sort((a, b) => b.generation_twh - a.generation_twh);
  const x = d3.scaleLinear()
    .domain([0, d3.max(rows, (d) => d.generation_twh)])
    .nice()
    .range([margin.left, width - margin.right]);
  const y = d3.scaleBand()
    .domain(rows.map((d) => d.source))
    .range([margin.top, height - margin.bottom])
    .padding(0.28);

  const svg = d3.select(host).selectAll("svg").data([null]).join("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("height", height)
    .attr("role", "img")
    .attr("aria-labelledby", "bar-svg-title bar-svg-desc");

  svg.selectAll("title").data([null]).join("title").attr("id", "bar-svg-title").text(`World electricity generation by source in ${state.selectedYear}`);
  svg.selectAll("desc").data([null]).join("desc").attr("id", "bar-svg-desc").text("Horizontal bars rank nine sources by terawatt-hours. Each label also gives its percentage share.");

  svg.selectAll(".baseline").data([null]).join("line")
    .attr("class", "baseline")
    .attr("x1", margin.left).attr("x2", margin.left)
    .attr("y1", margin.top).attr("y2", height - margin.bottom);

  svg.selectAll(".bar-axis").data([null]).join("g")
    .attr("class", "bar-axis")
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(width < 480 ? 3 : 4).tickFormat((d) => d === 0 ? "0" : `${d / 1000}k`).tickSizeOuter(0));

  const bars = svg.selectAll(".bar-row").data(rows, (d) => d.source);
  const entering = bars.enter().append("g")
    .attr("class", "bar-row")
    .attr("data-source", (d) => d.source)
    .attr("tabindex", 0)
    .attr("role", "button")
    .style("--bar-color", (d) => colors.get(d.source));

  entering.append("text").attr("class", "bar-rank").attr("text-anchor", "end");
  entering.append("text").attr("class", "bar-source").attr("text-anchor", "end");
  entering.append("rect").attr("x", margin.left).attr("width", 0);
  entering.append("text").attr("class", "bar-value");

  const merged = entering.merge(bars)
    .attr("data-source", (d) => d.source)
    .attr("aria-label", (d) => `${d.source}: ${formatTwh(d.generation_twh)} terawatt-hours, ${formatShare(d.share_pct)} percent in ${d.year}. Focus or click to coordinate this source.`);

  addSourceInteractions(merged, (datum) => datum);

  const transition = d3.transition().duration(animate ? 420 : 0).ease(d3.easeCubicOut);
  merged.transition(transition).attr("transform", (d) => `translate(0,${y(d.source)})`);
  merged.select(".bar-rank")
    .attr("x", 17).attr("y", y.bandwidth() / 2 + 3)
    .attr("text-anchor", "middle")
    .text((d) => `${rows.indexOf(d) + 1}`);
  merged.select(".bar-source")
    .attr("x", margin.left - 8).attr("y", y.bandwidth() / 2 + 4)
    .style("font-size", width < 480 ? "10px" : "11px")
    .text((d) => d.source);
  merged.select("rect")
    .attr("height", y.bandwidth())
    .transition(transition)
    .attr("width", (d) => x(d.generation_twh) - margin.left);
  merged.select(".bar-value")
    .attr("y", y.bandwidth() / 2 + 4)
    .transition(transition)
    .attr("x", (d) => Math.min(x(d.generation_twh) + 7, width - margin.right + 6))
    .text((d) => `${formatTwh(d.generation_twh)} · ${formatShare(d.share_pct)}%`);

  bars.exit().remove();
  updateHighlight();
}

function updateYear(year) {
  state.selectedYear = +year;
  document.querySelector("#year-display").textContent = state.selectedYear;
  document.querySelector("#bar-year").textContent = state.selectedYear;

  const rows = state.byYear.get(state.selectedYear);
  const leader = d3.greatest(rows, (d) => d.generation_twh);
  const total = d3.sum(rows, (d) => d.generation_twh);
  document.querySelector("#summary-text").textContent = `${formatTwh(total)} TWh generated in ${state.selectedYear}. ${leader.source} ranks first at ${formatTwh(leader.generation_twh)} TWh (${formatShare(leader.share_pct)}%).`;
  updateSmallMultipleSelection();
  renderBars();
}

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function showError(error) {
  const message = document.querySelector("#chart-error");
  message.hidden = false;
  message.textContent = `The visualization could not load its local data: ${error.message}`;
  document.querySelector("#summary-text").textContent = "Data unavailable.";
}

async function init() {
  try {
    const data = await d3.csv(DATA_PATH, (row) => ({
      year: +row.year,
      source: row.source,
      generation_twh: +row.generation_twh,
      share_pct: +row.share_pct,
    }));
    if (!data.length || data.some((row) => !Number.isFinite(row.generation_twh) || !Number.isFinite(row.share_pct))) {
      throw new Error("The CSV is empty or contains invalid numeric values.");
    }

    state.data = data;
    state.years = [...new Set(data.map((row) => row.year))].sort(d3.ascending);
    state.sources = [...new Set(data.map((row) => row.source))];
    state.bySource = d3.group(data, (row) => row.source);
    state.byYear = d3.group(data, (row) => row.year);
    state.selectedYear = d3.max(state.years);
    state.shareMax = Math.ceil(d3.max(data, (row) => row.share_pct) / 5) * 5;

    slider
      .attr("min", d3.min(state.years))
      .attr("max", d3.max(state.years))
      .property("value", state.selectedYear)
      .on("input", (event) => updateYear(event.target.value));
    document.querySelector("#range-start").textContent = d3.min(state.years);
    document.querySelector("#range-end").textContent = d3.max(state.years);
    document.querySelector("#scale-note").textContent = `All panels use the same 0–${state.shareMax}% scale.`;

    d3.select("#clear-highlight").on("click", () => {
      state.lockedSource = null;
      state.hoverSource = null;
      d3.select("#clear-highlight").property("disabled", true);
      hideTooltip();
      updateHighlight();
    });

    renderSmallMultiples();
    updateYear(state.selectedYear);

    let resizeTimer;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => renderBars(false), 120);
    });
  } catch (error) {
    showError(error);
  }
}

init();
