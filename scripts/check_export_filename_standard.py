import re
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    main_py = project_root / "main.py"
    text = main_py.read_text(encoding="utf-8")

    pattern = re.compile(
        r'@app\.get\("([^"]*?/export)"\)[\s\S]*?async def [\s\S]*?return response',
        re.MULTILINE,
    )
    blocks = pattern.findall(text)
    if not blocks:
        print("No export routes found.")
        return 0

    route_block_pattern = re.compile(
        r'@app\.get\("([^"]*?/export)"\)([\s\S]*?)return response',
        re.MULTILINE,
    )
    failed = []
    for route, block in route_block_pattern.findall(text):
        if "_set_csv_download_headers(" not in block:
            failed.append(route)

    if failed:
        print("Export filename standard check failed:")
        for r in failed:
            print(f" - {r} does not use _set_csv_download_headers")
        return 1

    print("Export filename standard check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
