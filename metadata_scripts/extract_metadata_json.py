import os
import subprocess
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_CONFIG = yaml.safe_load((Path(__file__).parent / "extract_metadata_json.yaml").read_text())
INPUT_DIRECTORY = _CONFIG["input_directory"]
OUTPUT_DIRECTORY = _CONFIG["output_directory"]
WORKERS = int(_CONFIG.get("workers", min(4, os.cpu_count() or 2)))


def _run_exiftool(args):
    tiff, output = args
    if output.exists():
        return output, "skipped"
    result = subprocess.run(
        ["exiftool", "-j", "-a", "-u", "-g1", str(tiff)],
        capture_output=True,
        text=True,
    )
    output.write_text(result.stdout, encoding="utf-8")
    return output, "created"


def prompt_dir(label, default):
    val = input(f"{label} [{default}]: ").strip()
    return Path(val) if val else Path(default)


def main():
    input_dir  = prompt_dir("Input directory (TIFF files)", INPUT_DIRECTORY)
    output_dir = prompt_dir("Output directory (JSON files)", OUTPUT_DIRECTORY)

    print(f"\n  Input  : {input_dir.resolve()}")
    print(f"  Output : {output_dir.resolve()}")

    tiffs = sorted(input_dir.rglob("*.[tT][iI][fF]") )
    tiffs += sorted(input_dir.rglob("*.[tT][iI][fF][fF]"))
    tiffs = sorted(set(tiffs))

    if not tiffs:
        print("\nNo TIFF files found.")
        return

    print(f"\n  {len(tiffs)} TIFF file(s) found")
    print()

    answer = input("Continue? [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    jobs = [
        (tiff, output_dir / f"{tiff.stem}-Metadata.json")
        for tiff in tiffs
    ]

    print(f"\nRunning exiftool on {len(jobs)} file(s) with {WORKERS} worker(s)...\n")

    created = 0
    skipped = 0
    errors  = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_run_exiftool, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                output, status = future.result()
                if status == "created":
                    created += 1
                    print(f"  Created  {output.name}")
                else:
                    skipped += 1
                    print(f"  Skipped  {output.name}")
            except Exception as e:
                errors += 1
                tiff, _ = futures[future]
                print(f"  ERROR    {tiff.name}: {e}")

    print(f"\nDone. {created} created, {skipped} skipped, {errors} error(s).")
    print(f"JSON files are in: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
