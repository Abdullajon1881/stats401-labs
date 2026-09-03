const COLUMNS = [
  { key: "key", label: "Key", numeric: true },
  { key: "scientific_name", label: "Scientific name", numeric: false },
  { key: "species", label: "Species", numeric: false },
  { key: "family", label: "Family", numeric: false },
  { key: "country", label: "Country", numeric: false },
  { key: "year", label: "Year", numeric: true },
  { key: "month", label: "Month", numeric: true },
  { key: "basis_of_record", label: "Basis of record", numeric: false }
];

let sortColumn = null;
let ascending = true;

d3.csv("../data/lab3_data.csv", d => ({
  key: +d.key,
  scientific_name: d.scientific_name,
  species: d.species,
  family: d.family,
  country: d.country,
  year: +d.year,
  month: +d.month,
  basis_of_record: d.basis_of_record
})).then(data => {
  const table = d3.select("#data-table");
  d3.select("#record-count").text(data.length);

  const headers = table.select("thead")
    .selectAll("th")
    .data(COLUMNS)
    .join("th")
    .on("click", (event, column) => {
      // a new column always starts ascending; the same column toggles
      if (sortColumn === column.key) {
        ascending = !ascending;
      } else {
        sortColumn = column.key;
        ascending = true;
      }
      draw();
    });

  function compare(a, b, column) {
    if (column.numeric) {
      const x = a[column.key];
      const y = b[column.key];
      // blank cells become NaN, so keep them at the bottom either way
      if (Number.isNaN(x) && Number.isNaN(y)) return 0;
      if (Number.isNaN(x)) return 1;
      if (Number.isNaN(y)) return -1;
      return ascending ? d3.ascending(x, y) : d3.descending(x, y);
    }
    const x = a[column.key] || "";
    const y = b[column.key] || "";
    return ascending ? d3.ascending(x, y) : d3.descending(x, y);
  }

  function draw() {
    const column = COLUMNS.find(c => c.key === sortColumn);
    const rows = column ? data.slice().sort((a, b) => compare(a, b, column)) : data;

    headers.text(d =>
      d.key === sortColumn ? `${d.label} ${ascending ? "▲" : "▼"}` : d.label
    );

    table.select("tbody")
      .selectAll("tr")
      .data(rows)
      .join("tr")
      .selectAll("td")
      .data(row => COLUMNS.map(c => {
        const value = row[c.key];
        return c.numeric && Number.isNaN(value) ? "" : value;
      }))
      .join("td")
      .text(d => d);
  }

  draw();
});
