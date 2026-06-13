#!/bin/bash

SOLR_URL="http://localhost:8983/solr"
COLLECTION="mhs_photos"

curl -X POST "$SOLR_URL/$COLLECTION/schema" \
  -H "Content-Type: application/json" \
  -d '{
    "replace-field": { "name": "subject",  "type": "text_general", "stored": true },
    "replace-field": { "name": "keywords", "type": "text_general", "stored": true },
    "replace-field": { "name": "headline", "type": "text_general", "stored": true }
  }'

echo ""
echo "Field types updated. Re-run solr_upload.py to re-index documents."
