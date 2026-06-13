import csv
import re
import shutil
import subprocess
import yaml
from pathlib import Path

_CONFIG = yaml.safe_load((Path(__file__).parent / "find_published_dir.yaml").read_text())
INPUT_DIRECTORY = _CONFIG["input_directory"]
METADATA_DIRECTORY = _CONFIG["metadata_directory"]
OUTPUT_DIRECTORY = _CONFIG["output_directory"]


MONTHS = (
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"
)
# Day is optional — month + year is sufficient; also matches YYYY-MM-DD
DATE_PATTERN = re.compile(
    rf"\b({MONTHS}\s+(?:\d{{1,2}}\s+)?\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\b",
    re.IGNORECASE,
)
# Matches "published", "published:" or "published;" case-insensitively
PUBLISHED_RE = re.compile(r"\bpublished[;:]?", re.IGNORECASE)


def extract_subject(text):
    xmp_match = re.search(r"---- XMP-dc ----\n(.*?)(?=\n---- |\Z)", text, re.DOTALL)
    if xmp_match:
        found = re.findall(r"Subject\s+:\s+(.+)", xmp_match.group(1))
        return found[0].strip() if found else ""
    return ""


def extract_iptc_keywords_raw(text):
    iptc_match = re.search(r"---- IPTC ----\n(.*?)(?=\n---- |\Z)", text, re.DOTALL)
    if not iptc_match:
        return ""
    found = re.findall(r"Keywords\s+:\s+(.+)", iptc_match.group(1))
    return found[0].strip() if found else ""


def extract_tags(text):
    found = re.findall(r"^Tags\s+:\s+(.+)", text, re.MULTILINE | re.IGNORECASE)
    return found[0].strip() if found else ""


def has_published(value):
    return bool(PUBLISHED_RE.search(value))


def extract_date(value):
    m = DATE_PATTERN.search(value)
    return m.group(1) if m else ""


def in_published_folder(path):
    return any(part.lower() == "published" for part in path.parts)


def extract_metadata(input_dir, metadata_dir):
    for tiff in sorted(input_dir.rglob("*.[tT][iI][fF][fF]")):
        if in_published_folder(tiff.relative_to(input_dir)):
            continue
        relative = tiff.relative_to(input_dir)
        output = metadata_dir / relative.parent / (tiff.stem + "-Metadata.txt")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            print(f"Skipped (exists) {output}")
            continue
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
    seen_tiffs = set()

    for filepath in sorted(metadata_dir.rglob("*Metadata.txt")):
        if in_published_folder(filepath.relative_to(metadata_dir)):
            continue
        text = filepath.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

        subject = extract_subject(text)
        iptc_keywords = extract_iptc_keywords_raw(text)
        tags = extract_tags(text)

        pub_in_subject = has_published(subject)
        pub_in_keywords = has_published(iptc_keywords)
        pub_in_tags = has_published(tags)

        combined = f"{subject} {iptc_keywords} {tags}"
        if not (pub_in_subject or pub_in_keywords or pub_in_tags):
            continue
        date = extract_date(combined)

        relative = filepath.relative_to(metadata_dir)
        tiff_name = re.sub(r"-Metadata\.txt$", ".tiff", filepath.name, flags=re.IGNORECASE)

        if tiff_name in seen_tiffs:
            continue
        seen_tiffs.add(tiff_name)

        tiff_uri = (input_dir.resolve() / relative.parent / tiff_name).as_uri()
        metadata_uri = filepath.resolve().as_uri()

        results.append({
            "filename": filepath.name,
            "date": date,
            "tiff_name": tiff_name,
            "tiff_relative": relative.parent / tiff_name,
            "tiff_uri": tiff_uri,
            "metadata_uri": metadata_uri,
            "subject": subject,
            "iptc_keywords": iptc_keywords,
            "tags": tags,
            "published_in_subject": pub_in_subject,
            "published_in_keywords": pub_in_keywords,
            "published_in_tags": pub_in_tags,
        })

    results.sort(key=lambda r: r["tiff_name"])

    output_html = output_dir / "published_files.html"
    rows = ""
    for r in results:
        def flag(val):
            color = "#d4edda" if val else "#f8d7da"
            return f'<td style="background:{color}">{val}</td>'

        rows += (
            f"<tr>"
            f"<td class=\"copyable\">{r['tiff_name']}</td>"
            f"<td>{r['date']}</td>"
            f"<td><a href=\"{r['tiff_uri']}\">{r['tiff_name']}</a></td>"
            f"<td><a href=\"{r['metadata_uri']}\">{r['filename']}</a></td>"
            f"<td>{r['subject']}</td>"
            f"<td>{r['iptc_keywords']}</td>"
            f"<td>{r['tags']}</td>"
            f"{flag(r['published_in_subject'])}"
            f"{flag(r['published_in_keywords'])}"
            f"{flag(r['published_in_tags'])}"
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
<thead><tr>
  <th>Filename (click to copy)</th>
  <th>Date</th>
  <th>TIFF</th>
  <th>Metadata</th>
  <th>Subject</th>
  <th>IPTC Keywords</th>
  <th>Tags</th>
  <th>Published in Subject</th>
  <th>Published in Keywords</th>
  <th>Published in Tags</th>
</tr></thead>
<tbody>
{rows}</tbody>
</table>
</body>
</html>"""

    output_html.write_text(html, encoding="utf-8")

    output_csv = output_dir / "published_files.csv"
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "filename", "date", "tiff_name", "metadata_file",
            "subject", "iptc_keywords", "tags",
            "published_in_subject", "published_in_keywords", "published_in_tags",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "filename": r["filename"],
                "date": r["date"],
                "tiff_name": r["tiff_name"],
                "metadata_file": r["filename"],
                "subject": r["subject"],
                "iptc_keywords": r["iptc_keywords"],
                "tags": r["tags"],
                "published_in_subject": r["published_in_subject"],
                "published_in_keywords": r["published_in_keywords"],
                "published_in_tags": r["published_in_tags"],
            })

    copied = 0
    for r in results:
        src = input_dir / r["tiff_relative"]
        if src.exists():
            dest_dir = src.parent / "published"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), dest_dir / r["tiff_name"])
            copied += 1
        else:
            print(f"Warning: TIFF not found, skipping move: {src}")

    print(f"Found {len(results)} file(s) with 'Published' + date in subject or keywords.")
    print(f"Moved {copied} TIFF(s) to published/ subfolder(s)")
    print(f"Results written to {output_html} and {output_csv}")


if __name__ == "__main__":
    main()
