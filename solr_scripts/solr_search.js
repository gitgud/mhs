const SOLR_URL = "http://localhost:8983/solr/mhs_photos/select";

async function doSearch() {
  const raw = document.getElementById("query").value.trim();
  const publishedOnly = document.getElementById("publishedOnly").checked;
  const q = publishedOnly ? `${raw} +published`.trim() : raw;
  const rows = parseInt(document.getElementById("limit").value, 10) || 10;
  const status = document.getElementById("status");
  const results = document.getElementById("results");

  if (!raw) {
    status.textContent = "Enter a search term.";
    status.className = "status";
    results.innerHTML = "";
    return;
  }

  status.textContent = "Searching…";
  status.className = "status";
  results.innerHTML = "";

  const params = new URLSearchParams({
    q,
    wt: "json",
    rows,
    defType: "edismax",
    qf: "subject keywords headline description",
    fl: "id,file_name,directory,subject,keywords,headline,description",
  });

  try {
    const resp = await fetch(`${SOLR_URL}?${params}`);
    if (!resp.ok) throw new Error(`Solr returned ${resp.status}`);
    const data = await resp.json();

    const docs = data.response?.docs ?? [];
    const total = data.response?.numFound ?? 0;

    status.textContent = `${total.toLocaleString()} result${total !== 1 ? "s" : ""} — showing ${docs.length}`;
    status.className = "status";

    if (docs.length === 0) {
      results.innerHTML = '<p class="no-results">No results found.</p>';
      return;
    }

    results.innerHTML = docs
      .map((doc) => {
        const dir = Array.isArray(doc.directory)
          ? doc.directory[0]
          : (doc.directory ?? "");
        const fname = Array.isArray(doc.file_name)
          ? doc.file_name[0]
          : (doc.file_name ?? "");
        const filePath = dir && fname ? `file://${dir}/${fname}` : "";

        return `
        <a class="card" ${filePath ? `href="${esc(filePath)}"` : ""} ${filePath ? 'target="_blank"' : ""}>
          <div class="info">
            <div class="headline">${esc(Array.isArray(doc.headline) ? doc.headline[0] : (doc.headline ?? fname ?? doc.id))}</div>
            <div class="filename">${esc(fname)}${dir ? " · " + esc(dir) : ""}</div>
            ${doc.subject ? `<div class="field"><span>Subject</span>${esc(Array.isArray(doc.subject) ? doc.subject[0] : doc.subject)}</div>` : ""}
            ${doc.keywords ? `<div class="field"><span>Keywords</span>${esc(Array.isArray(doc.keywords) ? doc.keywords.join(", ") : doc.keywords)}</div>` : ""}
            ${doc.description ? `<div class="field"><span>Description</span>${esc(Array.isArray(doc.description) ? doc.description[0] : doc.description)}</div>` : ""}
          </div>
        </a>`;
      })
      .join("");
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
    status.className = "status error";
  }
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.getElementById("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  doSearch();
});
