
import json
import os
import sys
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    
    import requests
except ImportError:
    sys.exit("Missing dependency: pip3 install requests")

_CONFIG = yaml.safe_load((Path(__file__).parent / "solr_upload.yaml").read_text())
METADATA_DIRECTORY = _CONFIG["metadata_directory"]
SOLR_URL = _CONFIG["solr_url"].rstrip("/")
SOLR_COLLECTION = _CONFIG["solr_collection"]
BATCH_SIZE = int(_CONFIG.get("batch_size", 50))
WORKERS = int(_CONFIG.get("workers", min(4, os.cpu_count() or 2)))


def _group(record, *keys):
    """Return the first non-empty value found across the given group.field paths."""
    for group, field in keys:
        val = (record.get(group) or {}).get(field, "")
        if val:
            return str(val).strip()
    return ""


def json_to_solr_doc(filepath, record):
    filename = filepath.stem.removesuffix("-Metadata")
    return {
        "id": filename,
        "file_name": _group(record, ("System", "FileName")),
        "directory": _group(record, ("System", "Directory")),
        "subject": _group(record, ("XMP-dc", "Subject")),
        "keywords": _group(record, ("IPTC", "Keywords"), ("IPTC2", "Keywords"), ("XMP-iptcCore", "Keywords")),
        "headline": _group(record, ("IPTC", "Headline"), ("IPTC2", "Headline")),
        "description": _group(record, ("XMP-dc", "Description"), ("IPTC2", "Caption-Abstract"), ("IFD0", "XPComment")),
    }


def parse_metadata_file(filepath):
    text = filepath.read_text(encoding="utf-8", errors="replace")
    data = json.loads(text)
    if not data:
        return None
    return json_to_solr_doc(filepath, data[0])


def post_batch(batch):
    url = f"{SOLR_URL}/{SOLR_COLLECTION}/update"
    resp = requests.post(url, json=batch, params={"commit": "false"}, timeout=30)
    resp.raise_for_status()
    return len(batch)


def commit():
    url = f"{SOLR_URL}/{SOLR_COLLECTION}/update"
    requests.post(url, json={"commit": {}}, timeout=30).raise_for_status()


def prompt_dir(label, default):
    val = input(f"{label} [{default}]: ").strip()
    return Path(val) if val else Path(default)


def main():
    metadata_dir = prompt_dir("Metadata directory", METADATA_DIRECTORY)

    print(f"\nMetadata : {metadata_dir.resolve()}")
    print(f"Solr     : {SOLR_URL}/{SOLR_COLLECTION}")
    print()

    answer = input("Continue? [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        return

    all_files = sorted(metadata_dir.rglob("*-Metadata.json"))
    if not all_files:
        print("No *-Metadata.json files found.")
        return

    print(f"Parsing {len(all_files)} file(s)...")
    docs = []
    for fp in all_files:
        doc = parse_metadata_file(fp)
        if doc:
            docs.append(doc)

    print(f"Uploading {len(docs)} document(s) in batches of {BATCH_SIZE} with {WORKERS} worker(s)...")

    batches = [docs[i:i + BATCH_SIZE] for i in range(0, len(docs), BATCH_SIZE)]
    uploaded = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(post_batch, b): b for b in batches}
        for future in as_completed(futures):
            try:
                uploaded += future.result()
                print(f"  Uploaded {uploaded}/{len(docs)}")
            except Exception as e:
                errors += 1
                print(f"  ERROR: {e}")

    if errors == 0:
        commit()
        print(f"\nDone. {uploaded} document(s) committed to {SOLR_COLLECTION}.")
    else:
        print(f"\n{errors} batch(es) failed. Skipping commit — fix errors and re-run.")


if __name__ == "__main__":
    main()
