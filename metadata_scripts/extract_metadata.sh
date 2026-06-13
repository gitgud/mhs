#!/bin/bash

DIR="${1:-.}"

if [[ ! -d "$DIR" ]]; then
    echo "Error: '$DIR' is not a directory"
    exit 1
fi

for tiff in "$DIR"/*.tif "$DIR"/*.TIF "$DIR"/*.tiff "$DIR"/*.TIFF; do
    [[ -f "$tiff" ]] || continue
    base="${tiff%.*}"
    exiftool -a -u -g1 "$tiff" > "${base}-Metadata.txt"
    echo "Created ${base}.txt"
done
