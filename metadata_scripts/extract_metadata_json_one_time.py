import subprocess
import sys
from pathlib import Path

# ── Parameters ────────────────────────────────────────────────────────────────
INPUT_DIR = Path(__file__).parent
OUTPUT_DIR = Path(__file__).parent
# ─────────────────────────────────────────────────────────────────────────────

def main():
    tiffs = sorted(INPUT_DIR.glob("*.[tT][iI][fF]")) + sorted(INPUT_DIR.glob("*.[tT][iI][fF][fF]"))

    if not tiffs:
        print(f"No .tif/.tiff files found in {INPUT_DIR}")
        sys.exit(0)

    print(f"Found {len(tiffs)} file(s) in {INPUT_DIR}\n")

    for tiff in tiffs:
        output = OUTPUT_DIR / (tiff.stem + "-Metadata.json")
        with open(output, "w") as f:
            subprocess.run(
                ["exiftool", "-a", "-u", "-g1", "-json", str(tiff)],
                stdout=f,
                stderr=subprocess.DEVNULL,
            )
        print(f"Created {output.name}")

    print(f"\nDone. {len(tiffs)} file(s) processed.")

if __name__ == "__main__":
    main()
