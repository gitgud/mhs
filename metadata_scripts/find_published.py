import csv
import re
import subprocess
from pathlib import Path

INPUT_DIRECTORY = "/Users/kale/Desktop/TEST"
METADATA_DIRECTORY = "/Users/kale/Desktop/test_output"
OUTPUT_DIRECTORY = "/Users/kale/Desktop/test_output"

MONTHS = (
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"
)
DATE_PATTERN = re.compile(rf"\b({MONTHS}\s+\d{{1,2}}\s+\d{{4}})\b", re.IGNORECASE)


def extract_iptc_keywords(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    iptc_match = re.search(r"---- IPTC ----\n(.*?)(?=\n---- |\Z)", text, re.DOTALL)
    if not iptc_match:
        return []
    iptc_section = iptc_match.group(1)
    return re.findall(r"Keywords\s+:\s+(.+)", iptc_section)


def extract_date(keywords_list):
    for kw in keywords_list:
        m = DATE_PATTERN.search(kw)
        if m:
            return m.group(1)
    return ""


def extract_metadata(input_dir, metadata_dir):
    for tiff in sorted(input_dir.rglob("*.[tT][iI][fF][fF]")):
        relative = tiff.relative_to(input_dir)
        output = metadata_dir / relative.parent / (tiff.stem + "-Metadata.txt")
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            subprocess.run(["exiftool", "-a", "-u", "-g1", str(tiff)], stdout=f)
        print(f"Created {output}")


def prompt_dir(label, default):
    val = input(f"{label} [{default}]: ").strip()
    return Path(val) if val else Path(default)


def main():
    input_dir = prompt_dir("Input directory (TIFF files)", INPUT_DIRECTORY)
    metadata_dir = prompt_dir("Metadata directory", METADATA_DIRECTORY)
    output_dir = prompt_dir("Output directory (HTML/CSV)", OUTPUT_DIRECTORY)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    extract_metadata(input_dir, metadata_dir)
    results = []

    for filepath in sorted(metadata_dir.rglob("*Metadata.txt")):
        text = filepath.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        keywords = extract_iptc_keywords(text)
        if not keywords:
            continue

        combined = " ".join(keywords)
        if "published" not in combined.lower():
            continue

        relative = filepath.relative_to(metadata_dir)
        tiff_name = re.sub(r"-Metadata\.txt$", ".tiff", filepath.name, flags=re.IGNORECASE)
        tiff_uri = (input_dir.resolve() / relative.parent / tiff_name).as_uri()
        metadata_uri = filepath.resolve().as_uri()

        results.append({
            "filename": filepath.name,
            "date": extract_date(keywords),
            "tiff_name": tiff_name,
            "tiff_uri": tiff_uri,
            "metadata_uri": metadata_uri,
            "keywords": ", ".join(keywords),
        })

    output_html = output_dir / "published_files.html"
    rows = ""
    for r in results:
        rows += (
            f"<tr>"
            f"<td class=\"copyable\">{r['tiff_name']}</td>"
            f"<td>{r['date']}</td>"
            f"<td><a href=\"{r['tiff_uri']}\">{r['tiff_name']}</a></td>"
            f"<td><a href=\"{r['metadata_uri']}\">{r['filename']}</a></td>"
            f"<td>{r['keywords']}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; padding: 1em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f0f0f0; }}
  td.copyable {{ cursor: pointer; }}
  td.copyable:hover {{ background: #fffbe6; }}
</style>
<script>
  document.addEventListener("click", function(e) {{
    var td = e.target.closest("td.copyable");
    if (!td) return;
    navigator.clipboard.writeText(td.textContent.trim()).then(function() {{
      var orig = td.style.background;
      td.style.background = "#d4edda";
      setTimeout(function() {{ td.style.background = orig; }}, 600);
    }});
  }});
</script>
</head>
<body>
<table>
<thead><tr><th>Filename (click to copy)</th><th>Date</th><th>TIFF</th><th>Metadata</th><th>Keywords</th></tr></thead>
<tbody>
{rows}</tbody>
</table>
</body>
</html>"""

    output_html.write_text(html, encoding="utf-8")

    output_csv = output_dir / "published_files.csv"
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "date", "tiff_name", "metadata_file", "keywords"])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "filename": r["filename"],
                "date": r["date"],
                "tiff_name": r["tiff_name"],
                "metadata_file": r["filename"],
                "keywords": r["keywords"],
            })

    print(f"Found {len(results)} file(s) with 'Published' in keywords.")
    print(f"Results written to {output_html} and {output_csv}")


if __name__ == "__main__":
    main()
