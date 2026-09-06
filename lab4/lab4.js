const SENTIMENTS = ["Negative", "Neutral", "Positive"];
const CLASSES = ["Disaster-related", "Non-disaster"];

const margin = { top: 30, right: 170, bottom: 60, left: 70 };
const width = 640;
const height = 420;
const innerWidth = width - margin.left - margin.right;
const innerHeight = height - margin.top - margin.bottom;

const color = d3.scaleOrdinal()
  .domain(SENTIMENTS)
  .range(["#d1495b", "#9aa5b1", "#2a9d8f"]);

const tooltip = d3.select("#tooltip");

function showTooltip(event, d) {
  tooltip
    .style("display", "block")
    .html(
      "<strong>" + d.disaster_class + "</strong><br>" +
      "Sentiment: " + d.sentiment + "<br>" +
      "Tweets: " + d.count + "<br>" +
      "Share: " + (d.proportion * 100).toFixed(1) + "%"
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

d3.csv("../data/lab4_sentiment_by_disaster.csv", d => ({
  disaster_class: d.disaster_class,
  sentiment: d.sentiment,
  count: +d.count,
  proportion: +d.proportion
})).then(rows => {
  const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width)
    .attr("height", height);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand()
    .domain(CLASSES)
    .range([0, innerWidth])
    .padding(0.35);

  const y = d3.scaleLinear()
    .domain([0, 1])
    .range([innerHeight, 0]);

  // stack each class from Negative at the bottom to Positive at the top
  const segments = [];
  CLASSES.forEach(className => {
    let offset = 0;
    SENTIMENTS.forEach(sentiment => {
      const row = rows.find(r => r.disaster_class === className && r.sentiment === sentiment);
      if (!row) return;
      segments.push(Object.assign({}, row, { start: offset, end: offset + row.proportion }));
      offset += row.proportion;
    });
  });

  g.selectAll(".lab4-segment")
    .data(segments)
    .join("rect")
    .attr("class", "lab4-segment")
    .attr("x", d => x(d.disaster_class))
    .attr("y", d => y(d.end))
    .attr("width", x.bandwidth())
    .attr("height", d => y(d.start) - y(d.end))
    .attr("fill", d => color(d.sentiment))
    .on("mouseover", showTooltip)
    .on("mousemove", moveTooltip)
    .on("mouseout", hideTooltip);

  // percentage label inside each segment that is tall enough to hold one
  g.selectAll(".lab4-segment-label")
    .data(segments.filter(d => d.proportion >= 0.06))
    .join("text")
    .attr("class", "lab4-segment-label")
    .attr("x", d => x(d.disaster_class) + x.bandwidth() / 2)
    .attr("y", d => (y(d.start) + y(d.end)) / 2)
    .attr("dy", "0.35em")
    .text(d => (d.proportion * 100).toFixed(1) + "%");

  g.append("g")
    .attr("transform", `translate(0,${innerHeight})`)
    .call(d3.axisBottom(x));

  g.append("g")
    .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format(".0%")));

  g.append("text")
    .attr("class", "lab4-axis-title")
    .attr("transform", "rotate(-90)")
    .attr("x", -innerHeight / 2)
    .attr("y", -48)
    .text("Share of tweets");

  g.append("text")
    .attr("class", "lab4-axis-title")
    .attr("x", innerWidth / 2)
    .attr("y", innerHeight + 46)
    .text("Tweet class");

  svg.append("text")
    .attr("class", "lab4-chart-title")
    .attr("x", margin.left)
    .attr("y", 18)
    .text("Estimated sentiment of disaster vs non-disaster tweets");

  const legend = g.append("g")
    .attr("transform", `translate(${innerWidth + 24},0)`);

  legend.append("text")
    .attr("class", "lab4-legend-title")
    .attr("y", 11)
    .text("Predicted sentiment");

  legend.selectAll(".lab4-legend-key")
    .data(SENTIMENTS)
    .join("g")
    .attr("class", "lab4-legend-key")
    .attr("transform", (d, i) => `translate(0,${26 + i * 22})`)
    .each(function (d) {
      const key = d3.select(this);
      key.append("rect").attr("width", 13).attr("height", 13).attr("fill", color(d));
      key.append("text").attr("class", "lab4-legend-text").attr("x", 19).attr("y", 11).text(d);
    });

  const totals = CLASSES.map(className => {
    const total = d3.sum(rows.filter(r => r.disaster_class === className), r => r.count);
    return className + ": " + total;
  });
  d3.select("#chart-totals").text("Tweets per class — " + totals.join(", "));
});
