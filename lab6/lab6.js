(function () {
  "use strict";

  const width = 1080;
  const height = 600;
  const numberFormat = d3.format(",");
  const statuses = ["Increase", "Unchanged", "Decrease"];
  const statusColor = d3.scaleOrdinal()
    .domain(statuses)
    .range(["#2b7a4b", "#6b7280", "#b6473e"]);
  const tooltip = document.querySelector("#tooltip");

  function buildLegend() {
    const legend = document.querySelector("#status-legend");
    const items = statuses.map((status) => {
      const item = document.createElement("div");
      const swatch = document.createElement("span");
      const label = document.createElement("span");

      item.className = "lab6-legend-item";
      swatch.className = "lab6-swatch";
      swatch.style.backgroundColor = statusColor(status);
      swatch.setAttribute("aria-hidden", "true");
      label.textContent = status;
      item.append(swatch, label);
      return item;
    });
    legend.replaceChildren(...items);
  }

  function hierarchyFor(data) {
    return d3.hierarchy(data)
      .sum((d) => d.gdp || 0)
      .sort((a, b) => b.value - a.value || d3.ascending(a.data.name, b.data.name));
  }

  function ancestorsFor(leaf) {
    const ancestors = leaf.ancestors();
    return {
      area: ancestors.find((node) => node.depth === 2).data.name,
      continent: ancestors.find((node) => node.depth === 1).data.name
    };
  }

  function accessibleName(leaf) {
    const { area, continent } = ancestorsFor(leaf);
    return `${leaf.data.name}. ${area}, ${continent}. GDP ${numberFormat(leaf.data.gdp)} billion US dollars. Status ${leaf.data.status}.`;
  }

  function truncateLabel(label, availableWidth, fontSize) {
    const maxCharacters = Math.floor(availableWidth / (fontSize * 0.58));
    if (maxCharacters < 4) return "";
    if (label.length <= maxCharacters) return label;
    return `${label.slice(0, Math.max(1, maxCharacters - 1))}…`;
  }

  function usesVerticalContinentLabel(node) {
    return node.depth === 1 && node.x1 - node.x0 < 75 && node.y1 - node.y0 > 80;
  }

  function tooltipContent(leaf) {
    const { area, continent } = ancestorsFor(leaf);
    const title = document.createElement("strong");
    title.textContent = leaf.data.name;

    const rows = [
      ["Continent", continent],
      ["Area", area],
      ["GDP", `$${numberFormat(leaf.data.gdp)} billion`],
      ["Status", leaf.data.status]
    ].map(([label, value]) => {
      const row = document.createElement("p");
      const key = document.createElement("span");
      key.textContent = `${label}: `;
      row.append(key, document.createTextNode(value));
      return row;
    });

    tooltip.replaceChildren(title, ...rows);
  }

  function positionTooltip(clientX, clientY) {
    const gap = 12;
    const bounds = tooltip.getBoundingClientRect();
    let left = clientX + gap;
    let top = clientY + gap;

    if (left + bounds.width > window.innerWidth - gap) {
      left = clientX - bounds.width - gap;
    }
    if (top + bounds.height > window.innerHeight - gap) {
      top = clientY - bounds.height - gap;
    }

    tooltip.style.left = `${Math.max(gap, left)}px`;
    tooltip.style.top = `${Math.max(gap, top)}px`;
  }

  function showTooltip(leaf, clientX, clientY) {
    tooltipContent(leaf);
    tooltip.classList.add("is-visible");
    tooltip.setAttribute("aria-hidden", "false");
    positionTooltip(clientX, clientY);
  }

  function hideTooltip() {
    tooltip.classList.remove("is-visible");
    tooltip.setAttribute("aria-hidden", "true");
  }

  function renderTreemap(data, containerSelector, tile, chartName) {
    const root = hierarchyFor(data);
    const layout = d3.treemap()
      .tile(tile)
      .size([width, height])
      .round(false)
      .paddingOuter((node) => node.depth === 0 ? 4 : node.depth === 1 ? 2 : 0)
      .paddingInner(1)
      .paddingTop((node) => {
        if (node.depth === 1) return 24;
        if (node.depth === 2) return node.value >= 700 ? 16 : 2;
        return 0;
      });

    layout(root);

    const svg = d3.select(containerSelector)
      .append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("role", "group")
      .attr("aria-label", `${chartName} treemap of GDP by continent, area, and country`)
      .attr("data-layout", chartName);

    const allNodes = root.descendants().filter((node) => node.depth > 0);
    allNodes.forEach((node, index) => {
      node.clipId = `${chartName.toLowerCase().replace(/[^a-z]/g, "")}-clip-${index}`;
    });

    svg.append("defs")
      .selectAll("clipPath")
      .data(allNodes)
      .join("clipPath")
      .attr("id", (node) => node.clipId)
      .append("rect")
      .attr("x", (node) => node.children ? node.x0 : 0)
      .attr("y", (node) => node.children ? node.y0 : 0)
      .attr("width", (node) => Math.max(0, node.x1 - node.x0))
      .attr("height", (node) => Math.max(0, node.y1 - node.y0));

    const countries = svg.append("g")
      .attr("class", "lab6-country-layer")
      .selectAll("g")
      .data(root.leaves())
      .join("g")
      .attr("class", "lab6-country")
      .attr("data-country", (leaf) => leaf.data.name)
      .attr("tabindex", 0)
      .attr("role", "img")
      .attr("aria-label", accessibleName)
      .attr("transform", (leaf) => `translate(${leaf.x0},${leaf.y0})`);

    countries.append("rect")
      .attr("width", (leaf) => Math.max(0, leaf.x1 - leaf.x0))
      .attr("height", (leaf) => Math.max(0, leaf.y1 - leaf.y0))
      .attr("fill", (leaf) => statusColor(leaf.data.status));

    const countryLabels = countries.append("text")
      .attr("class", "lab6-country-label")
      .attr("x", 6)
      .attr("y", 16)
      .attr("clip-path", (leaf) => `url(#${leaf.clipId})`)
      .style("display", (leaf) => {
        const cellWidth = leaf.x1 - leaf.x0;
        const cellHeight = leaf.y1 - leaf.y0;
        return cellWidth >= 56 && cellHeight >= 27 ? null : "none";
      });

    countryLabels.append("tspan")
      .text((leaf) => truncateLabel(leaf.data.name, leaf.x1 - leaf.x0 - 12, 12));

    countryLabels.append("tspan")
      .attr("class", "lab6-country-value")
      .attr("x", 6)
      .attr("dy", 15)
      .style("display", (leaf) => {
        const cellWidth = leaf.x1 - leaf.x0;
        const cellHeight = leaf.y1 - leaf.y0;
        return cellWidth >= 68 && cellHeight >= 45 ? null : "none";
      })
      .text((leaf) => `$${numberFormat(leaf.data.gdp)}B`);

    countries
      .on("mouseenter focus", function (event, leaf) {
        d3.select(this).classed("is-active", true);
        const bounds = this.getBoundingClientRect();
        const clientX = event.type === "focus" ? bounds.left + bounds.width / 2 : event.clientX;
        const clientY = event.type === "focus" ? bounds.top + bounds.height / 2 : event.clientY;
        showTooltip(leaf, clientX, clientY);
      })
      .on("mousemove", function (event) {
        positionTooltip(event.clientX, event.clientY);
      })
      .on("mouseleave blur", function () {
        d3.select(this).classed("is-active", false);
        hideTooltip();
      });

    const parentLayer = svg.append("g").attr("class", "lab6-parent-layer");
    const parents = parentLayer.selectAll("g")
      .data(root.descendants().filter((node) => node.depth === 1 || node.depth === 2))
      .join("g");

    parents.append("rect")
      .attr("class", (node) => node.depth === 1 ? "lab6-continent-boundary" : "lab6-area-boundary")
      .attr("x", (node) => node.x0)
      .attr("y", (node) => node.y0)
      .attr("width", (node) => Math.max(0, node.x1 - node.x0))
      .attr("height", (node) => Math.max(0, node.y1 - node.y0));

    parents.append("text")
      .attr("class", (node) => [
        "lab6-parent-label",
        node.depth === 1 ? "lab6-continent-label" : "lab6-area-label",
        usesVerticalContinentLabel(node) ? "lab6-vertical-label" : ""
      ].join(" ").trim())
      .attr("x", (node) => node.x0 + (usesVerticalContinentLabel(node) ? 13 : 6))
      .attr("y", (node) => node.y0 + (usesVerticalContinentLabel(node) ? 7 : node.depth === 1 ? 18 : 13))
      .attr("transform", (node) => usesVerticalContinentLabel(node)
        ? `rotate(90,${node.x0 + 13},${node.y0 + 7})`
        : null)
      .attr("clip-path", (node) => usesVerticalContinentLabel(node) ? null : `url(#${node.clipId})`)
      .text((node) => {
        if (node.depth === 2 && node.value < 700) return "";
        const nodeWidth = usesVerticalContinentLabel(node)
          ? node.y1 - node.y0 - 12
          : node.x1 - node.x0 - 12;
        const fontSize = node.depth === 1 ? 14 : 10.5;
        return truncateLabel(node.data.name, nodeWidth, fontSize);
      });

    return root;
  }

  function updateSummary(root) {
    const continentCount = root.children.length;
    const areaCount = root.descendants().filter((node) => node.depth === 2).length;
    const countryCount = root.leaves().length;
    document.querySelector("#data-summary").textContent =
      `${countryCount} countries · ${continentCount} continents · ${areaCount} areas · Total GDP $${numberFormat(root.value)}B`;
  }

  function showLoadError(error) {
    const errorBox = document.querySelector("#load-error");
    errorBox.textContent = "The GDP hierarchy could not be loaded. Please refresh the page or check the data file.";
    errorBox.hidden = false;
    document.querySelector("#data-summary").textContent = "GDP hierarchy unavailable.";
    console.error(error);
  }

  buildLegend();

  d3.json("../data/lab6_assignment_gdp.json")
    .then((data) => {
      const squarifyRoot = renderTreemap(
        data,
        "#squarify-chart",
        d3.treemapSquarify,
        "Squarify"
      );
      renderTreemap(
        data,
        "#slicedice-chart",
        d3.treemapSliceDice,
        "Slice-Dice"
      );
      updateSummary(squarifyRoot);
    })
    .catch(showLoadError);
}());
