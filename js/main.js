const width = 640;
const height = 360;
const barWidth = 50;
const barGap = 20;
const labelSpace = 40;

const svg = d3.select("#chart")
  .append("svg")
  .attr("width", width)
  .attr("height", height);

d3.csv("../data/students.csv", d => ({
  name: d.name,
  score: +d.score
})).then(data => {
  const chartHeight = height - labelSpace;

  const y = d3.scaleLinear()
    .domain([0, 100])
    .range([0, chartHeight]);

  const x = i => i * (barWidth + barGap) + barGap;

  svg.selectAll("rect")
    .data(data)
    .join("rect")
    .attr("class", "bar")
    .attr("x", (d, i) => x(i))
    .attr("y", d => chartHeight - y(d.score))
    .attr("width", barWidth)
    .attr("height", d => y(d.score));

  // score, then name, under each bar
  svg.selectAll(".score-label")
    .data(data)
    .join("text")
    .attr("class", "label score-label")
    .attr("x", (d, i) => x(i) + barWidth / 2)
    .attr("y", chartHeight + 16)
    .text(d => d.score);

  svg.selectAll(".name-label")
    .data(data)
    .join("text")
    .attr("class", "label name-label")
    .attr("x", (d, i) => x(i) + barWidth / 2)
    .attr("y", chartHeight + 32)
    .text(d => d.name);
});
