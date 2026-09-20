// Lab 7: Temporal Data Visualization
// A 60-day commercial network among 12 companies. Node positions are solved
// once with d3.forceSimulation() over the full-period relationship set and then
// held fixed, so each daily frame only changes the things that change in the
// data: the active links, their width and style, node size, and the summary.

(function () {
  "use strict";

  const WIDTH = 980;
  const HEIGHT = 580;
  const FIRST_DAY = 1;
  const LAST_DAY = 60;
  const FRAME_MS = 550;
  const LINK_OPACITY = 0.82;

  const REGIONS = ["Asia", "Europe", "North America"];
  const SECTORS = [
    "Manufacturing",
    "Logistics",
    "Retail",
    "Food",
    "Technology",
    "Wholesale",
    "Materials"
  ];
  const TRANSACTION_TYPES = ["goods", "shipping", "components", "materials", "services"];

  // Sector hues are kept in one family per business area and deliberately away
  // from the link palette below, so a circle is never confused with a line.
  const sectorColor = d3.scaleOrdinal()
    .domain(SECTORS)
    .range(["#4e79a7", "#8bb1cf", "#b07aa1", "#e9a03b", "#3d7f6e", "#7d6c55", "#9c5b52"]);

  const typeColor = d3.scaleOrdinal()
    .domain(TRANSACTION_TYPES)
    .range(["#2f6f4f", "#1f6f9a", "#b4632c", "#8a6d1f", "#6c4f9c"]);

  const parseDate = d3.timeParse("%Y-%m-%d");
  const formatDay = d3.timeFormat("%B %-d, %Y");
  const formatUsd = d3.format("$,.0f");
  const formatUsdExact = d3.format("$,.2f");

  const tooltip = document.querySelector("#tooltip");

  const state = {
    day: FIRST_DAY,
    timer: null
  };

  // ---------------------------------------------------------------------------
  // tooltip: content is built with DOM nodes and textContent, never innerHTML,
  // so values coming out of the CSV files are never parsed as markup
  // ---------------------------------------------------------------------------

  function renderTooltip(title, subtitle, rows) {
    const heading = document.createElement("strong");
    heading.textContent = title;

    const parts = [heading];
    if (subtitle) {
      const sub = document.createElement("p");
      sub.className = "lab7-tooltip-sub";
      sub.textContent = subtitle;
      parts.push(sub);
    }

    rows.forEach(([label, value]) => {
      const row = document.createElement("p");
      const key = document.createElement("span");
      key.textContent = `${label}: `;
      row.append(key, document.createTextNode(value));
      parts.push(row);
    });

    tooltip.replaceChildren(...parts);
  }

  function positionTooltip(clientX, clientY) {
    const gap = 14;
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

  function showTooltip(clientX, clientY) {
    tooltip.classList.add("is-visible");
    tooltip.setAttribute("aria-hidden", "false");
    positionTooltip(clientX, clientY);
  }

  function hideTooltip() {
    tooltip.classList.remove("is-visible");
    tooltip.setAttribute("aria-hidden", "true");
  }

  // ---------------------------------------------------------------------------
  // data preparation
  // ---------------------------------------------------------------------------

  // Relationships are undirected, so the two company ids are sorted before the
  // key is built. Without this, c06-c09 on one day and c09-c06 on the next would
  // look like two different relationships to the keyed join.
  function pairKey(sourceId, targetId) {
    return sourceId < targetId
      ? `${sourceId}--${targetId}`
      : `${targetId}--${sourceId}`;
  }

  function prepare(companyRows, transactionRows) {
    const companies = companyRows.map((row) => ({
      id: row.id,
      name: row.company_name,
      sector: row.sector,
      region: row.region,
      // short on-canvas label; the tooltip always carries the full name
      shortName: row.company_name.split(" ")[0]
    }));

    const byId = new Map(companies.map((company) => [company.id, company]));

    const transactions = transactionRows.map((row) => ({
      date: parseDate(row.date),
      day: +row.day,
      // sourceId/targetId stay plain strings for the whole life of the page;
      // d3.forceLink() is only ever given the cloned layout links below, so it
      // can never overwrite these with node objects
      sourceId: row.source,
      targetId: row.target,
      key: pairKey(row.source, row.target),
      amount: +row.amount_usd,
      type: row.transaction_type,
      count: +row.transaction_count,
      crossRegion: byId.get(row.source).region !== byId.get(row.target).region
    }));

    const byDay = d3.group(transactions, (d) => d.day);
    const dayLinks = d3.range(FIRST_DAY, LAST_DAY + 1)
      .map((day) => byDay.get(day) || []);

    const dayDates = d3.range(FIRST_DAY, LAST_DAY + 1).map((day) => {
      const rows = byDay.get(day);
      return rows && rows.length ? rows[0].date : null;
    });

    return { companies, byId, transactions, dayLinks, dayDates };
  }

  function currentVolume(companyId, links) {
    return d3.sum(
      links.filter((d) => d.sourceId === companyId || d.targetId === companyId),
      (d) => d.amount
    );
  }

  function maxDailyVolume(companies, dayLinks) {
    let largest = 0;
    dayLinks.forEach((links) => {
      companies.forEach((company) => {
        largest = Math.max(largest, currentVolume(company.id, links));
      });
    });
    return largest;
  }

  // ---------------------------------------------------------------------------
  // layout: one simulation, run once, then frozen
  // ---------------------------------------------------------------------------

  function aggregateLayoutLinks(transactions) {
    const seen = new Map();
    transactions.forEach((d) => {
      const existing = seen.get(d.key);
      if (existing) {
        existing.days += 1;
        return;
      }
      seen.set(d.key, { source: d.sourceId, target: d.targetId, days: 1 });
    });
    return Array.from(seen.values());
  }

  function solveLayout(companies, transactions) {
    const bandX = d3.scalePoint()
      .domain(REGIONS)
      .range([170, WIDTH - 170]);

    // Deterministic seeding: without it the phyllotaxis default would still be
    // stable, but seeding by region makes the solved bands reproducible.
    const perRegion = new Map(REGIONS.map((region) => [region, 0]));
    companies.forEach((company) => {
      const index = perRegion.get(company.region);
      perRegion.set(company.region, index + 1);
      company.x = bandX(company.region);
      company.y = 150 + index * 90;
    });

    // forceLink() rewrites the source/target fields of whatever array it is
    // given, so it is handed cloned aggregate objects and never the transaction
    // rows the rest of the page reads.
    const layoutLinks = aggregateLayoutLinks(transactions);

    const simulation = d3.forceSimulation(companies)
      .force("link", d3.forceLink(layoutLinks)
        .id((d) => d.id)
        .distance(150)
        .strength(0.07))
      .force("charge", d3.forceManyBody().strength(-900))
      .force("center", d3.forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", d3.forceCollide(52))
      // Regional anchors hold each company inside its labelled band, so a line
      // that crosses a band boundary is always a cross-region relationship.
      // The link and charge forces then set the order within a band.
      .force("region", d3.forceX((d) => bandX(d.region)).strength(0.42))
      .force("vertical", d3.forceY(HEIGHT / 2).strength(0.035));

    simulation.stop();
    for (let i = 0; i < 500; i += 1) {
      simulation.tick();
    }

    const margin = 66;
    companies.forEach((company) => {
      company.x = Math.max(margin, Math.min(WIDTH - margin, company.x));
      company.y = Math.max(margin, Math.min(HEIGHT - margin - 14, company.y));
      // freeze the solved position for every one of the 60 frames
      company.fx = company.x;
      company.fy = company.y;
    });

    return { simulation, bandX };
  }

  // ---------------------------------------------------------------------------
  // drawing
  // ---------------------------------------------------------------------------

  function buildLegends(radiusScale, widthScale) {
    function swatchRow(container, items, colorFor) {
      const nodes = items.map((item) => {
        const row = document.createElement("div");
        const swatch = document.createElement("span");
        const label = document.createElement("span");
        row.className = "lab7-legend-item";
        swatch.className = "lab7-swatch";
        swatch.style.backgroundColor = colorFor(item);
        swatch.setAttribute("aria-hidden", "true");
        label.textContent = item;
        row.append(swatch, label);
        return row;
      });
      container.replaceChildren(...nodes);
    }

    swatchRow(document.querySelector("#sector-legend"), SECTORS, sectorColor);
    swatchRow(document.querySelector("#type-legend"), TRANSACTION_TYPES, typeColor);

    // node size
    const sizeSamples = [20000, 45000, 80000];
    const sizeSvg = d3.select("#size-legend")
      .append("svg")
      .attr("viewBox", "0 0 300 94")
      .attr("role", "img")
      .attr("aria-label", "Circle radius grows with the square root of the current-day transaction volume");
    sizeSamples.forEach((value, index) => {
      const cx = 42 + index * 96;
      sizeSvg.append("circle")
        .attr("class", "lab7-legend-node")
        .attr("cx", cx)
        .attr("cy", 36)
        .attr("r", radiusScale(value));
      sizeSvg.append("text")
        .attr("class", "lab7-legend-text")
        .attr("x", cx)
        .attr("y", 86)
        .text(formatUsd(value));
    });

    // inactive treatment
    const inactiveSvg = d3.select("#inactive-legend")
      .append("svg")
      .attr("viewBox", "0 0 300 62")
      .attr("role", "img")
      .attr("aria-label", "An inactive company is drawn small, faded and hollow in its usual position");
    inactiveSvg.append("circle")
      .attr("class", "lab7-legend-node lab7-legend-node-inactive")
      .attr("cx", 40)
      .attr("cy", 31)
      .attr("r", 7);
    inactiveSvg.append("text")
      .attr("class", "lab7-legend-text lab7-legend-text-left")
      .attr("x", 62)
      .attr("y", 36)
      .text("no relationship on this day");

    // link width
    const widthSamples = [8000, 18000, 34000];
    const widthSvg = d3.select("#width-legend")
      .append("svg")
      .attr("viewBox", "0 0 300 96")
      .attr("role", "img")
      .attr("aria-label", "Line thickness grows with the transaction amount in US dollars");
    widthSamples.forEach((value, index) => {
      const y = 20 + index * 28;
      widthSvg.append("line")
        .attr("class", "lab7-legend-line")
        .attr("x1", 12)
        .attr("x2", 132)
        .attr("y1", y)
        .attr("y2", y)
        .attr("stroke-width", widthScale(value));
      widthSvg.append("text")
        .attr("class", "lab7-legend-text lab7-legend-text-left")
        .attr("x", 144)
        .attr("y", y + 4)
        .text(formatUsd(value));
    });

    // link style
    const styleSvg = d3.select("#style-legend")
      .append("svg")
      .attr("viewBox", "0 0 300 70")
      .attr("role", "img")
      .attr("aria-label", "A solid line stays inside one region, a dashed line crosses between regions");
    [
      ["Same region", null, 20],
      ["Cross-region", "7 5", 50]
    ].forEach(([label, dash, y]) => {
      styleSvg.append("line")
        .attr("class", "lab7-legend-line")
        .attr("x1", 12)
        .attr("x2", 112)
        .attr("y1", y)
        .attr("y2", y)
        .attr("stroke-width", 3)
        .attr("stroke-dasharray", dash);
      styleSvg.append("text")
        .attr("class", "lab7-legend-text lab7-legend-text-left")
        .attr("x", 124)
        .attr("y", y + 4)
        .text(label);
    });
  }

  function build(data) {
    const { companies, byId, transactions, dayLinks, dayDates } = data;
    const { bandX } = solveLayout(companies, transactions);

    const radiusScale = d3.scaleSqrt()
      .domain([0, maxDailyVolume(companies, dayLinks)])
      .range([0, 30]);

    const widthScale = d3.scaleSqrt()
      .domain(d3.extent(transactions, (d) => d.amount))
      .range([2.2, 8]);

    const svg = d3.select("#network")
      .append("svg")
      .attr("viewBox", `0 0 ${WIDTH} ${HEIGHT}`)
      .attr("role", "img")
      .attr("aria-label", "Temporal node-link diagram of commercial relationships among twelve companies");

    // regional bands, drawn once, behind everything
    const bands = svg.append("g").attr("class", "lab7-bands");
    REGIONS.forEach((region, index) => {
      const centre = bandX(region);
      const half = (WIDTH / REGIONS.length) / 2;
      if (index > 0) {
        bands.append("line")
          .attr("class", "lab7-band-divider")
          .attr("x1", centre - half)
          .attr("x2", centre - half)
          .attr("y1", 34)
          .attr("y2", HEIGHT - 16);
      }
      bands.append("text")
        .attr("class", "lab7-band-label")
        .attr("x", centre)
        .attr("y", 24)
        .text(region);
    });

    const linkLayer = svg.append("g").attr("class", "lab7-link-layer");
    const nodeLayer = svg.append("g").attr("class", "lab7-node-layer");

    const nodes = nodeLayer.selectAll("g")
      .data(companies, (d) => d.id)
      .join("g")
      .attr("class", "lab7-node")
      .attr("data-company", (d) => d.id)
      .attr("transform", (d) => `translate(${d.x},${d.y})`)
      .attr("tabindex", 0)
      .attr("role", "img");

    nodes.append("circle")
      .attr("class", "lab7-node-circle")
      .attr("fill", (d) => sectorColor(d.sector));

    nodes.append("text")
      .attr("class", "lab7-node-label")
      .attr("y", 0)
      .text((d) => d.shortName);

    function nodeTooltip(company, links) {
      const incident = links.filter(
        (d) => d.sourceId === company.id || d.targetId === company.id
      );
      const partners = incident.map((d) => {
        const otherId = d.sourceId === company.id ? d.targetId : d.sourceId;
        return byId.get(otherId).name;
      });
      const rows = [
        ["Sector", company.sector],
        ["Region", company.region],
        ["Transaction volume today", formatUsdExact(d3.sum(incident, (d) => d.amount))],
        ["Active relationships today", String(incident.length)],
        ["Transactions today", String(d3.sum(incident, (d) => d.count))]
      ];
      if (partners.length) {
        rows.push(["Trading with", partners.sort(d3.ascending).join(", ")]);
      }
      renderTooltip(company.name, `${company.id} · Day ${state.day}`, rows);
    }

    function linkTooltip(link) {
      const source = byId.get(link.sourceId);
      const target = byId.get(link.targetId);
      renderTooltip(
        `${source.name} — ${target.name}`,
        `Day ${link.day} · ${formatDay(link.date)}`,
        [
          ["Transaction type", link.type],
          ["Amount", formatUsdExact(link.amount)],
          ["Transactions", String(link.count)],
          [
            "Regions",
            link.crossRegion
              ? `Cross-region (${source.region} — ${target.region})`
              : `Same region (${source.region})`
          ]
        ]
      );
    }

    function pointerFor(event, element) {
      if (event.type === "focus" || event.type === "focusin") {
        const box = element.getBoundingClientRect();
        return [box.left + box.width / 2, box.bottom];
      }
      return [event.clientX, event.clientY];
    }

    nodes
      .on("mouseenter focus", function (event, company) {
        d3.select(this).classed("is-active", true);
        nodeTooltip(company, dayLinks[state.day - FIRST_DAY]);
        const [x, y] = pointerFor(event, this);
        showTooltip(x, y);
      })
      .on("mousemove", (event) => positionTooltip(event.clientX, event.clientY))
      .on("mouseleave blur", function () {
        d3.select(this).classed("is-active", false);
        hideTooltip();
      });

    // -------------------------------------------------------------------------
    // one frame
    // -------------------------------------------------------------------------

    function reducedMotion() {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }

    function linkLabel(link) {
      const source = byId.get(link.sourceId);
      const target = byId.get(link.targetId);
      return `${source.name} and ${target.name}. ${link.type}, ${formatUsd(link.amount)}, `
        + `${link.crossRegion ? "cross-region" : "same region"}.`;
    }

    function updateLinks(links) {
      const duration = reducedMotion() ? 0 : 380;

      // Lines still fading out from an earlier frame are dropped before the
      // join so they can never be re-matched by a returning relationship. When
      // the user scrubs quickly this cuts a fade short, which is the right
      // trade: the current day must be correct, the transition need not replay.
      linkLayer.selectAll("line.is-exiting").interrupt().remove();

      linkLayer.selectAll("line")
        // keyed by the sorted company pair, never by array index, so a line that
        // survives from one day to the next is updated instead of re-created
        .data(links, (d) => d.key)
        .join(
          (enter) => enter.append("line")
            .attr("class", "lab7-link")
            .attr("role", "img")
            .attr("x1", (d) => byId.get(d.sourceId).x)
            .attr("y1", (d) => byId.get(d.sourceId).y)
            .attr("x2", (d) => byId.get(d.targetId).x)
            .attr("y2", (d) => byId.get(d.targetId).y)
            .attr("stroke", (d) => typeColor(d.type))
            .attr("stroke-width", (d) => widthScale(d.amount))
            .attr("stroke-dasharray", (d) => (d.crossRegion ? "7 5" : null))
            .attr("aria-label", linkLabel)
            .attr("opacity", 0)
            .on("mouseenter", function (event, link) {
              d3.select(this).classed("is-active", true);
              linkTooltip(link);
              showTooltip(event.clientX, event.clientY);
            })
            .on("mousemove", (event) => positionTooltip(event.clientX, event.clientY))
            .on("mouseleave", function () {
              d3.select(this).classed("is-active", false);
              hideTooltip();
            })
            .call((selection) => selection.transition().duration(duration)
              .attr("opacity", LINK_OPACITY)),
          (update) => update
            .attr("stroke-dasharray", (d) => (d.crossRegion ? "7 5" : null))
            .attr("aria-label", linkLabel)
            .call((selection) => selection.transition().duration(duration)
              .attr("stroke", (d) => typeColor(d.type))
              .attr("stroke-width", (d) => widthScale(d.amount))
              .attr("opacity", LINK_OPACITY)),
          (exit) => exit
            .classed("is-active", false)
            .classed("is-exiting", true)
            .call((selection) => selection.transition().duration(duration)
              .attr("opacity", 0)
              .remove())
        );
    }

    function updateNodes(links) {
      const duration = reducedMotion() ? 0 : 380;
      const volumes = new Map(
        companies.map((company) => [company.id, currentVolume(company.id, links)])
      );
      const degrees = new Map(companies.map((company) => [company.id, 0]));
      links.forEach((link) => {
        degrees.set(link.sourceId, degrees.get(link.sourceId) + 1);
        degrees.set(link.targetId, degrees.get(link.targetId) + 1);
      });

      function radiusFor(company) {
        const volume = volumes.get(company.id);
        return volume > 0 ? Math.max(9, radiusScale(volume)) : 7;
      }

      nodes
        .classed("is-inactive", (d) => volumes.get(d.id) === 0)
        .attr("aria-label", (d) => {
          const volume = volumes.get(d.id);
          const count = degrees.get(d.id);
          return volume > 0
            ? `${d.name}. ${d.sector}, ${d.region}. Day ${state.day}: ${formatUsd(volume)} across `
              + `${count} ${count === 1 ? "relationship" : "relationships"}.`
            : `${d.name}. ${d.sector}, ${d.region}. No relationship on day ${state.day}.`;
        });

      nodes.select("circle")
        .transition()
        .duration(duration)
        .attr("r", radiusFor);

      nodes.select("text")
        .transition()
        .duration(duration)
        .attr("y", (d) => radiusFor(d) + 15);
    }

    function updateSummary(links) {
      const active = new Set();
      links.forEach((link) => {
        active.add(link.sourceId);
        active.add(link.targetId);
      });
      const crossRegion = links.filter((link) => link.crossRegion).length;

      document.querySelector("#stat-companies").textContent = `${active.size} of 12`;
      document.querySelector("#stat-links").textContent = String(links.length);
      document.querySelector("#stat-value").textContent = formatUsd(
        d3.sum(links, (link) => link.amount)
      );
      document.querySelector("#stat-cross").textContent = links.length
        ? `${crossRegion} of ${links.length}`
        : "0";
    }

    function showDay(day) {
      state.day = day;
      const links = dayLinks[day - FIRST_DAY];
      const date = dayDates[day - FIRST_DAY];

      updateLinks(links);
      updateNodes(links);
      updateSummary(links);

      document.querySelector("#day-readout").textContent = date
        ? `Day ${day} · ${formatDay(date)}`
        : `Day ${day}`;
      document.querySelector("#time-slider").value = String(day);
      hideTooltip();
    }

    // -------------------------------------------------------------------------
    // play / pause / reset / slider
    // -------------------------------------------------------------------------

    const playButton = document.querySelector("#play");

    function setPlaying(isPlaying) {
      playButton.classList.toggle("is-playing", isPlaying);
      playButton.textContent = isPlaying ? "Playing…" : "Play";
      playButton.setAttribute("aria-pressed", isPlaying ? "true" : "false");
    }

    function pause() {
      if (state.timer) {
        state.timer.stop();
        state.timer = null;
      }
      setPlaying(false);
    }

    function play() {
      if (state.timer) return;
      // pressing Play at the end restarts from day 1
      if (state.day >= LAST_DAY) {
        showDay(FIRST_DAY);
      }
      setPlaying(true);
      state.timer = d3.interval(() => {
        const next = state.day + 1;
        showDay(next);
        if (next >= LAST_DAY) {
          pause();
        }
      }, FRAME_MS);
    }

    function reset() {
      pause();
      showDay(FIRST_DAY);
    }

    playButton.addEventListener("click", play);
    document.querySelector("#pause").addEventListener("click", pause);
    document.querySelector("#reset").addEventListener("click", reset);

    const slider = document.querySelector("#time-slider");
    slider.addEventListener("input", function () {
      pause();
      showDay(+this.value);
    });

    buildLegends(radiusScale, widthScale);

    const uniqueRelationships = new Set(transactions.map((d) => d.key)).size;
    document.querySelector("#data-summary").textContent =
      `${companies.length} companies · ${transactions.length} transaction records · `
      + `60 days (${formatDay(dayDates[0])} – ${formatDay(dayDates[LAST_DAY - 1])}) · `
      + `${uniqueRelationships} distinct relationships across the whole period`;

    setPlaying(false);
    showDay(FIRST_DAY);
  }

  function showLoadError(error) {
    const box = document.querySelector("#load-error");
    box.textContent = "The commercial network could not be loaded. "
      + "Please refresh the page or check that both Lab 7 data files are present.";
    box.hidden = false;
    document.querySelector("#data-summary").textContent = "Commercial network unavailable.";
    console.error(error);
  }

  Promise.all([
    d3.csv("../data/lab7_assignment_companies.csv"),
    d3.csv("../data/lab7_assignment_transactions_60days.csv")
  ])
    .then(([companyRows, transactionRows]) => {
      build(prepare(companyRows, transactionRows));
    })
    .catch(showLoadError);
}());
