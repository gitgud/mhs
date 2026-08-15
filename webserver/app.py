import mimetypes
import sys
from pathlib import Path

try:
    import requests
    import yaml
    from flask import Flask, abort, jsonify, request, send_file
except ImportError:
    sys.exit("Missing dependencies: pip3 install -r requirements.txt")

_CONFIG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
SOLR_URL = _CONFIG["solr_url"].rstrip("/")
SOLR_COLLECTION = _CONFIG["solr_collection"]
PHOTO_ROOT = Path(_CONFIG["photo_root"]).resolve()
HOST = _CONFIG.get("host", "0.0.0.0")
PORT = int(_CONFIG.get("port", 5001))

SEARCH_FIELDS = "id,file_name,directory,subject,keywords,headline,description"

app = Flask(__name__)


@app.after_request
def add_cors_headers(resp):
    # The search UI is opened as a local file:// page, so browser fetches to
    # this server are cross-origin. Allow them from anywhere on the network.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def _first(value):
    return value[0] if isinstance(value, list) else value


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing q parameter"}), 400

    rows = request.args.get("rows", default=10, type=int)
    if request.args.get("published", "false").lower() == "true":
        q = f"{q} +published"

    params = {
        "q": q,
        "wt": "json",
        "rows": rows,
        "defType": "edismax",
        "qf": "subject keywords headline description",
        "fl": SEARCH_FIELDS,
    }

    try:
        resp = requests.get(f"{SOLR_URL}/{SOLR_COLLECTION}/select", params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": f"Solr request failed: {e}"}), 502

    response = resp.json().get("response", {})
    return jsonify({
        "numFound": response.get("numFound", 0),
        "docs": response.get("docs", []),
    })


def _resolve_photo_path(doc_id):
    """Look up file_name/directory for doc_id in Solr and resolve them to a
    real path under PHOTO_ROOT. Never trusts a client-supplied path directly,
    to avoid path-traversal via crafted directory/file_name values."""
    try:
        resp = requests.get(f"{SOLR_URL}/{SOLR_COLLECTION}/get", params={"id": doc_id, "wt": "json"}, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    doc = resp.json().get("doc")
    if not doc:
        return None

    file_name = _first(doc.get("file_name"))
    directory = _first(doc.get("directory")) or ""
    if not file_name:
        return None

    candidate = (PHOTO_ROOT / directory / file_name).resolve()
    if candidate != PHOTO_ROOT and PHOTO_ROOT not in candidate.parents:
        return None
    return candidate


@app.route("/api/image/<path:doc_id>")
def api_image(doc_id):
    path = _resolve_photo_path(doc_id)
    if path is None or not path.is_file():
        abort(404)

    mimetype, _ = mimetypes.guess_type(path.name)
    return send_file(path, mimetype=mimetype or "application/octet-stream")


if __name__ == "__main__":
    print(f"Solr      : {SOLR_URL}/{SOLR_COLLECTION}")
    print(f"Photo root: {PHOTO_ROOT}")
    print(f"Listening : http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT)
