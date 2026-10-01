"""Import a downloaded Copernicus NetCDF: python -m app.feeds.import_copernicus file.nc.
Install the optional marine extra with uv sync --extra marine. No credentials are read.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.feeds.parsers.copernicus import import_subset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    data = import_subset(args.path)
    target = get_settings().data_dir / "copernicus" / "waves.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, allow_nan=False))
    temporary.replace(target)
    print(target)


if __name__ == "__main__":
    main()
