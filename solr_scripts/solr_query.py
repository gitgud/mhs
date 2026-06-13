import json
import yaml
import requests
from pathlib import Path

# ── Search parameters ─────────────────────────────────────────────────────────
SEARCH_TERM = "ndp"
MAX_RESULTS = 10
# ─────────────────────────────────────────────────────────────────────────────

_CONFIG = yaml.safe_load((Path(__file__).parent / "solr_upload.yaml").read_text())
SOLR_URL = _CONFIG["solr_url"].rstrip("/")
SOLR_COLLECTION = _CONFIG["solr_collection"]


def query(q, rows=MAX_RESULTS):
    params = {"q": q, "wt": "json", "rows": rows, "defType": "edismax", "qf": "subject keywords headline description", "fl": "id,file_name,directory,subject,keywords,headline,description"}
    url = f"{SOLR_URL}/{SOLR_COLLECTION}/select"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return url, resp.json()


def main():
    url, result = query(q=SEARCH_TERM, rows=MAX_RESULTS)
    print(url)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
