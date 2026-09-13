// Lab 5: Interactive Network Visualization
// Urban transit network: force-directed node-link diagram + adjacency matrix
// built from the same station and route tables.

const DISTRICTS = ["Central", "North", "South", "East", "West"];
const STATION_TYPES = ["Local", "Transfer", "Terminal"];
const ROUTE_TYPES = ["Metro", "Express", "Shuttle"];

// one district palette reused by every view
const districtColor = d3.scaleOrdinal()
  .domain(DISTRICTS)
  .range(["#4e79a7", "#59a14f", "#e15759", "#f28e2b", "#b07aa1"]);

// route colours are kept away from the district hues
const routeColor = d3.scaleOrdinal()
  .domain(ROUTE_TYPES)
  .range(["#2b2b2b", "#1b9e93", "#a6713f"]);

// a square rotated 45 degrees; d3.symbolDiamond is much taller than it is wide,
// so this keeps the three station shapes a similar size for the same area
const symbolDiamond = {
  draw(context, size) {
    const h = Math.sqrt(size / 2);
    context.moveTo(0, -h);
    context.lineTo(h, 0);
    context.lineTo(0, h);
    context.lineTo(-h, 0);
    context.closePath();
  }
};

const stationShape = d3.scaleOrdinal()
  .domain(STATION_TYPES)
  .range([d3.symbolCircle, d3.symbolSquare, symbolDiamond]);

// for a given symbol area, a square or diamond reaches 1.25x further from the
// centre than a circle does (half-diagonal versus radius)
const SHAPE_EXTENT = 1.25;

const formatCount = d3.format(",");
const tooltip = d3.select("#tooltip");

// ---------------------------------------------------------------------------
// tooltip helpers: content is built with textContent, never innerHTML
// ---------------------------------------------------------------------------

function renderTooltip(title, rows) {
  const el = tooltip.node();
  el.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = title;
  el.appendChild(heading);
  rows.forEach(([label, value]) => {
    const line = document.createElement("div");
    const key = document.createElement("span");
    key.className = "lab5-tooltip-label";
    key.textContent = label + ": ";
    line.appendChild(key);
    line.appendChild(document.createTextNode(value));
    el.appendChild(line);
  });
  tooltip.style("display", "block");
}

// keep the tooltip inside the viewport instead of letting it run off the edge
function placeTooltip(pageX, pageY) {
  const el = tooltip.node();
  const w = el.offsetWidth;
  const h = el.offsetHeight;
  const viewLeft = window.scrollX;
  const viewTop = window.scrollY;
  const viewRight = viewLeft + document.documentElement.clientWidth;
  const viewBottom = viewTop + document.documentElement.clientHeight;
  let left = pageX + 14;
  if (left + w > viewRight - 8) left = pageX - w - 14;
  if (left < viewLeft + 4) left = viewLeft + 4;
  let top = pageY + 14;
  if (top + h > viewBottom - 8) top = pageY - h - 14;
  if (top < viewTop + 4) top = viewTop + 4;
  tooltip.style("left", left + "px").style("top", top + "px");
}

function moveTooltip(event) {
  placeTooltip(event.pageX, event.pageY);
}

function placeTooltipAtElement(element) {
  const box = element.getBoundingClientRect();
  placeTooltip(box.right + window.scrollX, box.top + window.scrollY);
}

function hideTooltip() {
  tooltip.style("display", "none");
}

// ---------------------------------------------------------------------------
// data
// ---------------------------------------------------------------------------

function stationNumber(id) {
  return +id.slice(1);
}

// index the undirected links so both views can ask "who is next to X?"
function buildNetwork(stations, routes) {
  const neighbours = new Map(stations.map(s => [s.id, []]));
  routes.forEach(route => {
    neighbours.get(route.source).push({ id: route.target, route });
    neighbours.get(route.target).push({ id: route.source, route });
  });
  const nodes = stations.map(s => Object.assign({}, s, {
    number: stationNumber(s.id),
    degree: neighbours.get(s.id).length
  }));
  const byId = new Map(nodes.map(n => [n.id, n]));
  return { nodes, routes, neighbours, byId };
}

function connectionSummary(network, station) {
  return network.neighbours.get(station.id).map(c => {
    const other = network.byId.get(c.id);
    return `${other.name} (${c.route.routeType}, ${c.route.travelTime} min)`;
  });
}

function describeStation(network, station) {
  const count = station.degree;
  const noun = count === 1 ? "direct connection" : "direct connections";
  const parts = [
    `${station.name}.`,
    `${station.district} district.`,
    `${station.type} station.`,
    `${formatCount(station.passengers)} daily passengers.`,
    `${count} ${noun}.`
  ];
  if (count > 0) {
    const names = network.neighbours.get(station.id).map(c => network.byId.get(c.id).name);
    parts.push(`Connected to ${names.join(", ")}.`);
  }
  return parts.join(" ");
}

function showStationTooltip(network, station) {
  const rows = [
    ["District", station.district],
    ["Station type", station.type],
    ["Daily passengers", formatCount(station.passengers)],
    ["Direct connections", String(station.degree)]
  ];
  if (station.degree > 0) {
    rows.push(["Connected to", connectionSummary(network, station).join("; ")]);
  }
  renderTooltip(station.name, rows);
}

// routes carry station ids; after the force simulation binds them they carry node objects
function endpointId(endpoint) {
  return typeof endpoint === "object" ? endpoint.id : endpoint;
}

function showRouteTooltip(network, route) {
  const a = network.byId.get(endpointId(route.source));
  const b = network.byId.get(endpointId(route.target));
  renderTooltip(`${a.name} — ${b.name}`, [
    ["Route type", route.routeType],
    ["Travel time", `${route.travelTime} min`]
  ]);
}

// ---------------------------------------------------------------------------
// node-link view
// ---------------------------------------------------------------------------

function drawNodeLink(network) {
  const { nodes, neighbours } = network;
  // the simulation replaces source/target ids with node objects, so give it
  // its own copies and leave network.routes untouched for the matrix
  const links = network.routes.map(r => Object.assign({}, r));

  const width = 1100;
  const height = 640;

  // square-root scale so symbol area, not radius, follows passenger volume
  const radius = d3.scaleSqrt()
    .domain([0, d3.max(nodes, d => d.passengers)])
    .range([0, 15]);
  const linkWidth = d3.scaleLinear()
    .domain(d3.extent(links, d => d.travelTime))
    .range([1.2, 5.5]);
  const symbol = d3.symbol()
    .type(d => stationShape(d.type))
    .size(d => Math.PI * radius(d.passengers) ** 2);
  const extent = d => radius(d.passengers) * SHAPE_EXTENT;
  const collideRadius = d => extent(d) + 3;

  const svg = d3.select("#network")
    .append("svg")
    .attr("viewBox", [0, 0, width, height])
    .attr("role", "group")
    .attr("aria-label", "Force-directed diagram of 50 transit stations and 50 direct connections. Use Tab to move between stations.");

  const linkLayer = svg.append("g").attr("class", "lab5-links");
  const link = linkLayer.selectAll(".lab5-link")
    .data(links)
    .join("line")
    .attr("class", "lab5-link")
    .attr("stroke", d => routeColor(d.routeType))
    .attr("stroke-width", d => linkWidth(d.travelTime))
    .attr("stroke-opacity", 0.75);

  // wide invisible strokes so thin links are easy to hover
  const linkHit = linkLayer.selectAll(".lab5-link-hit")
    .data(links)
    .join("line")
    .attr("class", "lab5-link-hit")
    .on("mouseover", (event, d) => {
      showRouteTooltip(network, d);
      moveTooltip(event);
    })
    .on("mousemove", moveTooltip)
    .on("mouseout", hideTooltip);

  const node = svg.append("g")
    .attr("class", "lab5-nodes")
    .selectAll(".lab5-node")
    .data(nodes)
    .join("path")
    .attr("class", "lab5-node")
    .attr("d", symbol)
    .attr("fill", d => districtColor(d.district))
    .attr("stroke", "#333")
    .attr("stroke-width", 1)
    .attr("tabindex", 0)
    .attr("role", "button")
    .attr("aria-pressed", "false")
    .attr("aria-label", d => describeStation(network, d));

  // names appear on hover/focus; isolated stations keep a small label so they
  // are not mistaken for stray marks
  const label = svg.append("g")
    .attr("class", "lab5-labels")
    .selectAll("text")
    .data(nodes)
    .join("text")
    .attr("class", "lab5-node-label")
    .classed("is-isolated", d => d.degree === 0)
    .attr("dy", d => -(extent(d) + 5))
    .text(d => d.name);

  // start near the centre in a loose spiral so nothing flies in from a corner
  nodes.forEach((d, i) => {
    const angle = i * 2.4;
    const r = 14 * Math.sqrt(i);
    d.x = width / 2 + r * Math.cos(angle);
    d.y = height / 2 + r * Math.sin(angle);
  });

  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(64).strength(0.9))
    .force("charge", d3.forceManyBody().strength(-230).distanceMax(360))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide().radius(collideRadius).iterations(2))
    // a weaker pull in x than in y lets the network spread across the wide canvas
    .force("x", d3.forceX(width / 2).strength(0.02))
    .force("y", d3.forceY(height / 2).strength(0.07))
    .stop();

  const clampX = (d, x) => Math.max(collideRadius(d), Math.min(width - collideRadius(d), x));
  const clampY = (d, y) => Math.max(collideRadius(d), Math.min(height - collideRadius(d), y));

  function ticked() {
    nodes.forEach(d => {
      d.x = clampX(d, d.x);
      d.y = clampY(d, d.y);
    });
    link
      .attr("x1", d => d.source.x)
      .attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x)
      .attr("y2", d => d.target.y);
    linkHit
      .attr("x1", d => d.source.x)
      .attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x)
      .attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
    label.attr("x", d => d.x).attr("y", d => d.y);
  }

  // settle the layout before the first paint so the page opens on a stable
  // network; the simulation stays available for dragging and reset
  simulation.tick(300);
  ticked();
  simulation.on("tick", ticked);

  // --- highlighting -------------------------------------------------------

  const { focusStation, clearFocus } = createHighlighter(node, link, label, neighbours);
  let selectedNode = null;
  let isDragging = false;

  function restoreFocus() {
    if (selectedNode) focusStation(selectedNode);
    else clearFocus();
  }

  function toggleSelection(station) {
    selectedNode = selectedNode && selectedNode.id === station.id ? null : station;
    node.attr("aria-pressed", d => (selectedNode && d.id === selectedNode.id) ? "true" : "false");
    restoreFocus();
  }

  function clearSelection() {
    selectedNode = null;
    node.attr("aria-pressed", "false");
    clearFocus();
    hideTooltip();
  }

  node
    .on("mouseover", (event, d) => {
      if (isDragging) return;
      focusStation(d);
      showStationTooltip(network, d);
      moveTooltip(event);
    })
    .on("mousemove", event => {
      if (!isDragging) moveTooltip(event);
    })
    .on("mouseout", () => {
      if (isDragging) return;
      hideTooltip();
      restoreFocus();
    })
    .on("focus", (event, d) => {
      focusStation(d);
      showStationTooltip(network, d);
      placeTooltipAtElement(event.currentTarget);
    })
    .on("blur", () => {
      hideTooltip();
      restoreFocus();
    })
    .on("click", (event, d) => toggleSelection(d))
    .on("keydown", (event, d) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleSelection(d);
      } else if (event.key === "Escape") {
        clearSelection();
      }
    });

  // clicking empty canvas releases a pinned selection
  svg.on("click", event => {
    if (!event.target.closest(".lab5-node")) clearSelection();
  });

  // --- dragging -----------------------------------------------------------

  let dragMoved = false;

  node.call(d3.drag()
    .on("start", (event, d) => {
      dragMoved = false;
      isDragging = true;
      focusStation(d);
      d.fx = d.x;
      d.fy = d.y;
    })
    .on("drag", (event, d) => {
      // heat the simulation only once the pointer really moves, so a plain
      // click does not make the whole network wobble
      if (!dragMoved) {
        dragMoved = true;
        hideTooltip();
        simulation.alphaTarget(0.3).restart();
      }
      d.fx = clampX(d, event.x);
      d.fy = clampY(d, event.y);
    })
    .on("end", (event, d) => {
      isDragging = false;
      if (dragMoved && !event.active) simulation.alphaTarget(0);
      // a dragged station stays where it was dropped; a plain click does not pin it
      if (!dragMoved) {
        d.fx = null;
        d.fy = null;
      }
      const pointer = event.sourceEvent;
      if (pointer && pointer.type === "mouseup") {
        // the mouse is still over the station, so keep the hover state
        focusStation(d);
        showStationTooltip(network, d);
        placeTooltip(pointer.pageX, pointer.pageY);
      } else {
        restoreFocus();
      }
    }));

  d3.select("#reset-layout").on("click", () => {
    nodes.forEach(d => {
      d.fx = null;
      d.fy = null;
    });
    clearSelection();
    simulation.alpha(0.8).restart();
  });

  const isolated = nodes.filter(d => d.degree === 0).length;
  d3.select("#network-status").text(
    `Showing ${nodes.length} stations and ${links.length} direct connections; ${isolated} stations have no direct connection.`
  );

  buildNodeLinkLegend(radius, linkWidth);
}

// emphasise one station, its neighbours and incident links; mute the rest
function createHighlighter(node, link, label, neighbours) {
  const isIncident = (l, station) => l.source.id === station.id || l.target.id === station.id;

  function focusStation(station) {
    const nearby = new Set(neighbours.get(station.id).map(c => c.id));
    node
      .classed("is-focus", d => d.id === station.id)
      .classed("is-neighbour", d => nearby.has(d.id))
      .classed("is-muted", d => d.id !== station.id && !nearby.has(d.id));
    link
      .classed("is-incident", l => isIncident(l, station))
      .classed("is-muted", l => !isIncident(l, station));
    label
      .classed("is-visible", d => d.id === station.id || nearby.has(d.id))
      .classed("is-focus", d => d.id === station.id);
  }

  function clearFocus() {
    node.classed("is-focus is-neighbour is-muted", false);
    link.classed("is-incident is-muted", false);
    label.classed("is-visible is-focus", false);
  }

  return { focusStation, clearFocus };
}

// ---------------------------------------------------------------------------
// node-link legend (HTML, built from the same scales as the chart)
// ---------------------------------------------------------------------------

function legendGroup(container, title) {
  const group = container.append("div").attr("class", "lab5-legend-group");
  group.append("h3").text(title);
  return group;
}

function legendItem(group, text) {
  const item = group.append("div").attr("class", "lab5-legend-item");
  const svg = item.append("svg").attr("width", 40).attr("height", 34);
  item.append("span").text(text);
  return svg;
}

function buildNodeLinkLegend(radius, linkWidth) {
  const legend = d3.select("#network-legend");

  const districts = legendGroup(legend, "District → symbol colour");
  DISTRICTS.forEach(district => {
    legendItem(districts, district)
      .append("circle")
      .attr("cx", 20).attr("cy", 17).attr("r", 7)
      .attr("fill", districtColor(district))
      .attr("stroke", "#333");
  });

  const types = legendGroup(legend, "Station type → symbol shape");
  STATION_TYPES.forEach(type => {
    legendItem(types, type)
      .append("path")
      .attr("transform", "translate(20,17)")
      .attr("d", d3.symbol().type(stationShape(type)).size(150)())
      .attr("fill", "#bbb")
      .attr("stroke", "#333");
  });

  const sizes = legendGroup(legend, "Daily passengers → symbol area");
  [1500, 5000, 9500].forEach(p => {
    legendItem(sizes, formatCount(p) + " passengers")
      .append("circle")
      .attr("cx", 20).attr("cy", 17).attr("r", radius(p))
      .attr("fill", "#bbb")
      .attr("stroke", "#333");
  });
  sizes.append("p").attr("class", "lab5-legend-note")
    .text("Square-root scale: symbol area is proportional to average daily passengers.");

  const routes = legendGroup(legend, "Route type → line colour");
  ROUTE_TYPES.forEach(type => {
    legendItem(routes, type)
      .append("line")
      .attr("x1", 4).attr("x2", 36).attr("y1", 17).attr("y2", 17)
      .attr("stroke", routeColor(type))
      .attr("stroke-width", 3.5)
      .attr("stroke-linecap", "round");
  });

  const widths = legendGroup(legend, "Travel time → line width");
  [2, 9, 16].forEach(minutes => {
    legendItem(widths, minutes + " min")
      .append("line")
      .attr("x1", 4).attr("x2", 36).attr("y1", 17).attr("y2", 17)
      .attr("stroke", "#777")
      .attr("stroke-width", linkWidth(minutes))
      .attr("stroke-linecap", "round");
  });
  widths.append("p").attr("class", "lab5-legend-note")
    .text("Line width represents direct travel time only, not service frequency or importance.");
}

// ---------------------------------------------------------------------------
// adjacency matrix
// ---------------------------------------------------------------------------

function pairKey(a, b) {
  return a < b ? a + "|" + b : b + "|" + a;
}

function drawMatrix(network) {
  const { nodes, routes } = network;

  // deliberate ordering: district blocks, then station number inside each block
  const order = nodes.slice().sort((a, b) =>
    DISTRICTS.indexOf(a.district) - DISTRICTS.indexOf(b.district) || a.number - b.number);
  const index = new Map(order.map((d, i) => [d.id, i]));

  const cell = 13;
  const gap = 1;
  const step = cell + gap;
  const size = order.length * step - gap;
  const margin = { top: 160, left: 160, right: 12, bottom: 12 };

  const routeByPair = new Map(routes.map(r => [pairKey(r.source, r.target), r]));
  const cells = [];
  order.forEach((rowStation, i) => {
    order.forEach((colStation, j) => {
      const route = i === j ? null : (routeByPair.get(pairKey(rowStation.id, colStation.id)) || null);
      cells.push({ row: rowStation, col: colStation, i, j, route });
    });
  });

  const opacity = d3.scaleLinear()
    .domain(d3.extent(routes, r => r.travelTime))
    .range([0.4, 1]);
  const passengerBar = d3.scaleLinear()
    .domain([0, d3.max(nodes, d => d.passengers)])
    .range([0, 36]);
  const glyph = d3.symbol().type(d => stationShape(d.type)).size(30);

  const svg = d3.select("#matrix")
    .append("svg")
    .attr("width", margin.left + size + margin.right)
    .attr("height", margin.top + size + margin.bottom)
    .attr("role", "img")
    .attr("aria-label", "Adjacency matrix of the 50 stations. Rows and columns are ordered by district, then station number. A coloured cell marks a direct connection; colour is route type and opacity is travel time.");

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const cellGroup = g.append("g").attr("class", "lab5-matrix-cells");
  cellGroup.selectAll("rect")
    .data(cells)
    .join("rect")
    .attr("class", "lab5-matrix-cell")
    .attr("x", d => d.j * step)
    .attr("y", d => d.i * step)
    .attr("width", cell)
    .attr("height", cell)
    .attr("fill", d => d.route ? routeColor(d.route.routeType) : (d.i === d.j ? "#e4e4e4" : "#f3f3f3"))
    .attr("fill-opacity", d => d.route ? opacity(d.route.travelTime) : 1);

  // row and column highlight bars, drawn above the cells at low opacity
  const rowHighlight = g.append("rect").attr("class", "lab5-matrix-highlight")
    .attr("x", -margin.left + 2).attr("width", margin.left - 2 + size).attr("height", step)
    .style("display", "none");
  const colHighlight = g.append("rect").attr("class", "lab5-matrix-highlight")
    .attr("y", -margin.top + 2).attr("height", margin.top - 2 + size).attr("width", step)
    .style("display", "none");

  drawDistrictGuides(g, order, { step, gap, size });
  const { rowLabel, colLabel } = drawStationLabels(g, order, { step, cell, glyph, passengerBar });

  // --- interaction --------------------------------------------------------

  let activeCell = null;

  function highlight(i, j) {
    rowHighlight.style("display", i == null ? "none" : null).attr("y", i == null ? 0 : i * step - gap / 2);
    colHighlight.style("display", j == null ? "none" : null).attr("x", j == null ? 0 : j * step - gap / 2);
    rowLabel.classed("is-active", (d, k) => k === i);
    colLabel.classed("is-active", (d, k) => k === j);
  }

  function setActiveCell(target) {
    if (activeCell) d3.select(activeCell).attr("stroke", null);
    activeCell = target;
    if (activeCell) d3.select(activeCell).attr("stroke", "#111").attr("stroke-width", 1.5);
  }

  function clearMatrix() {
    highlight(null, null);
    setActiveCell(null);
    hideTooltip();
  }

  // one delegated listener for all 2,500 cells
  cellGroup
    .on("mouseover", event => {
      const d = d3.select(event.target).datum();
      if (!d || d.row === undefined) return;
      highlight(d.i, d.j);
      setActiveCell(event.target);
      if (d.route) {
        showRouteTooltip(network, d.route);
      } else if (d.i === d.j) {
        showStationTooltip(network, d.row);
      } else {
        renderTooltip(`${d.row.name} — ${d.col.name}`, [["Direct connection", "none"]]);
      }
      moveTooltip(event);
    })
    .on("mousemove", moveTooltip)
    .on("mouseleave", clearMatrix);

  rowLabel
    .on("mouseover", (event, d) => {
      highlight(index.get(d.id), null);
      showStationTooltip(network, d);
      moveTooltip(event);
    })
    .on("mousemove", moveTooltip)
    .on("mouseleave", clearMatrix);

  colLabel
    .on("mouseover", (event, d) => {
      highlight(null, index.get(d.id));
      showStationTooltip(network, d);
      moveTooltip(event);
    })
    .on("mousemove", moveTooltip)
    .on("mouseleave", clearMatrix);

  buildMatrixLegend(opacity);
}

// thin separators between district blocks plus district names in both margins
function drawDistrictGuides(g, order, { step, gap, size }) {
  const boundaries = [];
  order.forEach((d, i) => {
    if (i > 0 && d.district !== order[i - 1].district) boundaries.push(i * step - gap / 2);
  });
  g.selectAll(".lab5-matrix-separator-row")
    .data(boundaries)
    .join("line")
    .attr("class", "lab5-matrix-separator")
    .attr("x1", -34).attr("x2", size).attr("y1", d => d).attr("y2", d => d);
  g.selectAll(".lab5-matrix-separator-col")
    .data(boundaries)
    .join("line")
    .attr("class", "lab5-matrix-separator")
    .attr("y1", -34).attr("y2", size).attr("x1", d => d).attr("x2", d => d);

  const blocks = DISTRICTS.map(district => {
    const rows = order.map((d, i) => (d.district === district ? i : -1)).filter(i => i >= 0);
    return { district, centre: ((d3.min(rows) + d3.max(rows) + 1) / 2) * step - gap / 2 };
  });
  g.selectAll(".lab5-matrix-district-row")
    .data(blocks)
    .join("text")
    .attr("class", "lab5-matrix-district")
    .attr("transform", d => `translate(-146,${d.centre}) rotate(-90)`)
    .attr("text-anchor", "middle")
    .attr("fill", d => districtColor(d.district))
    .text(d => d.district);
  g.selectAll(".lab5-matrix-district-col")
    .data(blocks)
    .join("text")
    .attr("class", "lab5-matrix-district")
    .attr("x", d => d.centre)
    .attr("y", -146)
    .attr("text-anchor", "middle")
    .attr("fill", d => districtColor(d.district))
    .text(d => d.district);
}

// station labels for rows and columns: name coloured by district,
// station-type glyph, and a short bar for daily passengers
function drawStationLabels(g, order, { step, cell, glyph, passengerBar }) {
  const rowLabel = g.append("g").selectAll("g")
    .data(order)
    .join("g")
    .attr("class", "lab5-matrix-label")
    .attr("transform", (d, i) => `translate(0,${i * step + cell / 2})`);
  const colLabel = g.append("g").selectAll("g")
    .data(order)
    .join("g")
    .attr("class", "lab5-matrix-label")
    .attr("transform", (d, i) => `translate(${i * step + cell / 2},0) rotate(-90)`);

  [rowLabel, colLabel].forEach((sel, k) => {
    // in the rotated column frame "outward from the matrix" is +x, in rows it is -x
    const sign = k === 0 ? -1 : 1;
    sel.append("rect")
      .attr("x", sign < 0 ? -128 : 0).attr("y", -step / 2)
      .attr("width", 128).attr("height", step)
      .attr("fill", "transparent");
    sel.append("text")
      .attr("x", sign * 18)
      .attr("dy", "0.35em")
      .attr("text-anchor", sign < 0 ? "end" : "start")
      .attr("fill", d => districtColor(d.district))
      .text(d => d.name);
    sel.append("path")
      .attr("transform", `translate(${sign * 9},0)`)
      .attr("d", glyph)
      .attr("fill", d => districtColor(d.district))
      .attr("stroke", "#333")
      .attr("stroke-width", 0.8);
    sel.append("rect")
      .attr("x", d => sign < 0 ? -86 - passengerBar(d.passengers) : 86)
      .attr("y", -3.5)
      .attr("width", d => passengerBar(d.passengers))
      .attr("height", 7)
      .attr("fill", "#c4c4c4");
  });

  return { rowLabel, colLabel };
}

function buildMatrixLegend(opacity) {
  const legend = d3.select("#matrix-legend");
  const swatch = (item, fill, fillOpacity) => item.append("svg")
    .attr("width", 40).attr("height", 18)
    .append("rect").attr("x", 13).attr("y", 2).attr("width", 14).attr("height", 14)
    .attr("fill", fill).attr("fill-opacity", fillOpacity);

  legend.append("h3").text("Cell colour → route type");
  ROUTE_TYPES.forEach(type => {
    const item = legend.append("div").attr("class", "lab5-legend-item");
    swatch(item, routeColor(type), 1);
    item.append("span").text(type);
  });
  const none = legend.append("div").attr("class", "lab5-legend-item");
  swatch(none, "#f3f3f3", 1).attr("stroke", "#ddd");
  none.append("span").text("no direct connection");

  legend.append("h3").text("Cell opacity → travel time");
  [2, 9, 16].forEach(minutes => {
    const item = legend.append("div").attr("class", "lab5-legend-item");
    swatch(item, "#2b2b2b", opacity(minutes));
    item.append("span").text(minutes + " min");
  });
  legend.append("p").text("Darker means a longer direct travel time, not a stronger or busier connection.");

  legend.append("h3").text("Row and column labels");
  legend.append("p").text("Label colour is the station's district, the small symbol is its station type (circle local, square transfer, diamond terminal) and the grey bar length is its average daily passengers.");
  legend.append("p").text("Rows and columns use the same order: district (Central, North, South, East, West), then station number. The network is undirected, so the matrix is symmetric about the diagonal.");
}

// ---------------------------------------------------------------------------
// load both tables, then build both views from the same data
// ---------------------------------------------------------------------------

Promise.all([
  d3.csv("../data/lab5_assignment_stations.csv", d => ({
    id: d.id,
    name: d.station_name,
    district: d.district,
    passengers: +d.daily_passengers,
    type: d.station_type
  })),
  d3.csv("../data/lab5_assignment_routes.csv", d => ({
    source: d.source,
    target: d.target,
    travelTime: +d.travel_time_min,
    routeType: d.route_type
  }))
]).then(([stations, routes]) => {
  const network = buildNetwork(stations, routes);
  d3.select("#lab5-load-status").text(
    `Loaded ${stations.length} stations and ${routes.length} direct connections from the CSV files.`
  );
  drawNodeLink(network);
  drawMatrix(network);
}).catch(error => {
  console.error("Lab 5 data failed to load", error);
  d3.select("#lab5-load-status").text(
    "The station or route CSV could not be loaded. Open this page through a web server (for example python -m http.server) rather than as a local file."
  );
});
