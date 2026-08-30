const margin = { top: 20, right: 20, bottom: 130, left: 90 };
const popWidth = 400;
const panelGap = 70;
const tempWidth = 320;
const rowHeight = 26;

const regions = ["North", "South", "East", "West"];
const levels = ["Low", "Medium", "High"];

const color = d3.scaleOrdinal().domain(regions).range(d3.schemeTableau10);
const size = d3.scaleOrdinal().domain(levels).range([5, 8, 11]);

const tooltip = d3.select("#tooltip");

function showTooltip(event, d) {
  tooltip
    .style("display", "block")
    .html(
      "<strong>" + d.city + "</strong><br>" +
      "Population: " + d.population + " million<br>" +
      "Temperature: " + d.temp_c.toFixed(1) + " &deg;C<br>" +
      "Development: " + d.development_level + "<br>" +
      "Region: " + d.region
    );
}

function moveTooltip(event) {
  tooltip
    .style("left", (event.pageX + 14) + "px")
    .style("top", (event.pageY + 14) + "px");
}

function hideTooltip() {
  tooltip.style("display", "none");
}

d3.csv("../data/cities_multivariate.csv", d => ({
  city: d.city,
  population: +d.population,
  temp_c: +d.temp_c,
  development_level: d.development_level,
  region: d.region
})).then(data => {
  const innerHeight = data.length * rowHeight;
  const width = popWidth + panelGap + tempWidth + margin.left + margin.right;
  const height = innerHeight + margin.top + margin.bottom;

  const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width)
    .attr("height", height);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  // population is a ratio variable, so the bar scale starts at zero
  const x = d3.scaleLinear()
    .domain([0, d3.max(data, d => d.population)])
    .nice()
    .range([0, popWidth]);

  // temperature is an interval variable, so it uses its own extent
  const xTemp = d3.scaleLinear()
    .domain(d3.extent(data, d => d.temp_c))
    .nice()
    .range([0, tempWidth]);

  const y = d3.scaleBand()
    .domain(data.map(d => d.city))
    .range([0, innerHeight])
    .padding(0.25);

  const tempPanel = g.append("g")
    .attr("transform", `translate(${popWidth + panelGap},0)`);

  g.selectAll(".city-label")
    .data(data)
    .join("text")
    .attr("class", "city-label")
    .attr("x", -10)
    .attr("y", d => y(d.city) + y.bandwidth() / 2)
    .attr("dy", "0.35em")
    .text(d => d.city);

  g.selectAll(".city-bar")
    .data(data)
    .join("rect")
    .attr("class", "city-bar")
    .attr("x", 0)
    .attr("y", d => y(d.city))
    .attr("width", d => x(d.population))
    .attr("height", y.bandwidth())
    .attr("fill", d => color(d.region))
    .on("mouseover", showTooltip)
    .on("mousemove", moveTooltip)
    .on("mouseout", hideTooltip);

  tempPanel.selectAll(".temperature-dot")
    .data(data)
    .join("circle")
    .attr("class", "temperature-dot")
    .attr("cx", d => xTemp(d.temp_c))
    .attr("cy", d => y(d.city) + y.bandwidth() / 2)
    .attr("r", d => size(d.development_level))
    .attr("fill", d => color(d.region))
    .on("mouseover", showTooltip)
    .on("mousemove", moveTooltip)
    .on("mouseout", hideTooltip);

  g.append("g")
    .attr("transform", `translate(0,${innerHeight})`)
    .call(d3.axisBottom(x).ticks(5));

  tempPanel.append("g")
    .attr("transform", `translate(0,${innerHeight})`)
    .call(d3.axisBottom(xTemp).ticks(6));

  g.append("text")
    .attr("class", "axis-title")
    .attr("x", popWidth / 2)
    .attr("y", innerHeight + 42)
    .text("Population (millions)");

  tempPanel.append("text")
    .attr("class", "axis-title")
    .attr("x", tempWidth / 2)
    .attr("y", innerHeight + 42)
    .text("Average Temperature (°C)");

  const regionLegend = g.append("g")
    .attr("transform", `translate(0,${innerHeight + 72})`);

  regionLegend.append("text")
    .attr("class", "legend-title")
    .attr("y", 11)
    .text("Region");

  regionLegend.selectAll(".region-key")
    .data(regions)
    .join("g")
    .attr("class", "region-key")
    .attr("transform", (d, i) => `translate(${70 + i * 90},0)`)
    .each(function (d) {
      const key = d3.select(this);
      key.append("rect")
        .attr("width", 13)
        .attr("height", 13)
        .attr("fill", color(d));
      key.append("text")
        .attr("class", "legend-text")
        .attr("x", 19)
        .attr("y", 11)
        .text(d);
    });

  const sizeLegend = g.append("g")
    .attr("transform", `translate(0,${innerHeight + 104})`);

  sizeLegend.append("text")
    .attr("class", "legend-title")
    .attr("y", 11)
    .text("Development level");

  sizeLegend.selectAll(".size-key")
    .data(levels)
    .join("g")
    .attr("class", "size-key")
    .attr("transform", (d, i) => `translate(${130 + i * 90},0)`)
    .each(function (d) {
      const key = d3.select(this);
      key.append("circle")
        .attr("cx", 11)
        .attr("cy", 7)
        .attr("r", size(d))
        .attr("fill", "#888");
      key.append("text")
        .attr("class", "legend-text")
        .attr("x", 28)
        .attr("y", 11)
        .text(d);
    });
});
