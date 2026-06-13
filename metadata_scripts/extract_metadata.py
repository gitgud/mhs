import json
import os
import re
import subprocess
import yaml
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_CONFIG = yaml.safe_load((Path(__file__).parent / "find_published_dir.yaml").read_text())
INPUT_DIRECTORY = _CONFIG["input_directory"]
METADATA_DIRECTORY = _CONFIG["metadata_directory"]
WORKERS = int(_CONFIG.get("workers", min(8, os.cpu_count() or 4)))

# ── Metadata output format ────────────────────────────────────────────────────
# Enable either or both sidecar formats written by exiftool.
METADATA_TXT_FORMAT = False
METADATA_JSON_FORMAT = True


MONTHS = (
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"
)
DATE_PATTERN = re.compile(
    rf"\b({MONTHS}\s+(?:\d{{1,2}}\s+)?\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\b",
    re.IGNORECASE,
)
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


def _run_exiftool(tiff_output_fmt):
    tiff, output, fmt = tiff_output_fmt
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        return output, "skipped"
    cmd = ["exiftool", "-a", "-u", "-g1"]
    if fmt == "json":
        cmd.append("-json")
    with open(output, "w") as f:
        subprocess.run(cmd + [str(tiff)], stdout=f, stderr=subprocess.DEVNULL)
    return output, "created"


def extract_metadata(input_dir, metadata_dir):
    formats = (["txt"] if METADATA_TXT_FORMAT else []) + (["json"] if METADATA_JSON_FORMAT else [])
    jobs = []
    for tiff in sorted(input_dir.rglob("*.[tT][iI][fF][fF]")):
        if in_published_folder(tiff.relative_to(input_dir)):
            continue
        relative = tiff.relative_to(input_dir)
        for fmt in formats:
            output = metadata_dir / relative.parent / (tiff.stem + f"-Metadata.{fmt}")
            jobs.append((tiff, output, fmt))

    if not jobs:
        return

    print(f"Running exiftool on {len(jobs)} file(s) with {WORKERS} worker(s)...")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for output, status in pool.map(_run_exiftool, jobs):
            if status == "created":
                print(f"Created {output}")
            else:
                print(f"Skipped (exists) {output}")


def _fields_from_txt(text):
    return extract_subject(text), extract_iptc_keywords_raw(text), extract_tags(text)


def _fields_from_json(text):
    data = json.loads(text)
    if not data:
        return "", "", ""
    record = data[0]
    subject = str((record.get("XMP-dc") or {}).get("Subject", "")).strip()
    iptc_keywords = str((record.get("IPTC") or {}).get("Keywords", "")).strip()
    tags = ""
    for group in record.values():
        if isinstance(group, dict) and "Tags" in group:
            tags = str(group["Tags"]).strip()
            break
    return subject, iptc_keywords, tags


def _parse_metadata_file(args):
    filepath, metadata_dir, input_dir = args
    if in_published_folder(filepath.relative_to(metadata_dir)):
        return None
    text = filepath.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    if filepath.suffix.lower() == ".json":
        subject, iptc_keywords, tags = _fields_from_json(text)
    else:
        subject, iptc_keywords, tags = _fields_from_txt(text)

    pub_in_subject = has_published(subject)
    pub_in_keywords = has_published(iptc_keywords)
    pub_in_tags = has_published(tags)

    if not (pub_in_subject or pub_in_keywords or pub_in_tags):
        return None

    combined = f"{subject} {iptc_keywords} {tags}"
    date = extract_date(combined)
    relative = filepath.relative_to(metadata_dir)
    tiff_name = re.sub(r"-Metadata\.(txt|json)$", ".tiff", filepath.name, flags=re.IGNORECASE)
    tiff_uri = (input_dir.resolve() / relative.parent / tiff_name).as_uri()
    metadata_uri = filepath.resolve().as_uri()

    return {
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
    }


def prompt_dir(label, default):
    val = input(f"{label} [{default}]: ").strip()
    return Path(val) if val else Path(default)


def main():
    input_dir = prompt_dir("Input directory (TIFF files)", INPUT_DIRECTORY)
    metadata_dir = prompt_dir("Metadata directory", METADATA_DIRECTORY)

    print("\nDirectories:")
    print(f"  Input    : {input_dir.resolve()}")
    print(f"  Metadata : {metadata_dir.resolve()}")
    print(f"  Format   : txt={METADATA_TXT_FORMAT}  json={METADATA_JSON_FORMAT}")

    print("\nInput subdirectories to scan:")
    subdirs = sorted(p for p in input_dir.iterdir() if p.is_dir())
    if subdirs:
        for subdir in subdirs:
            sample_tiff = next(
                (t for t in subdir.rglob("*.[tT][iI][fF][fF]")
                 if not in_published_folder(t.relative_to(input_dir))),
                None,
            )
            sample_str = f"  (e.g. {sample_tiff.name})" if sample_tiff else "  (no TIFFs found)"
            print(f"  {subdir.name}/{sample_str}")
    else:
        print("  (no subdirectories — scanning input root directly)")
    print()

    answer = input("Continue? [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        return

    metadata_dir.mkdir(parents=True, exist_ok=True)

    extract_metadata(input_dir, metadata_dir)

    # Collect metadata files; when both formats are enabled, parse only txt to avoid double-counting
    if METADATA_TXT_FORMAT:
        all_files = sorted(metadata_dir.rglob("*Metadata.txt"), key=lambda p: p.stem)
    else:
        all_files = sorted(metadata_dir.rglob("*Metadata.json"))

    args = [(fp, metadata_dir, input_dir) for fp in all_files]

    seen_tiffs = set()
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for record in pool.map(_parse_metadata_file, args):
            if record is None:
                continue
            if record["tiff_name"] in seen_tiffs:
                continue
            seen_tiffs.add(record["tiff_name"])
            results.append(record)

    results.sort(key=lambda r: r["tiff_name"])

    print(f"\nFound {len(results)} file(s) with 'Published' + date in subject or keywords.")
    for r in results:
        print(f"  {r['tiff_name']}  ({r['date']})")


if __name__ == "__main__":
    main()
