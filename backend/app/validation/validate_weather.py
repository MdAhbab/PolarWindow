"""Fetch/re-score wind archives into a separate validation directory.

Examples: python -m app.validation.validate_weather hrrr --hours 1
          python -m app.validation.validate_weather gefs --score-only
The normal data/hindcast benchmark reports are preserved. Raw forecast caches
and observation CSVs remain under data/hindcast and are reused across runs.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from app.config import get_settings
from app.feeds import hindcast_hrrr, hindcast_reforecast


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("hrrr", "gefs"):
        raise SystemExit("Choose hrrr or gefs, followed by that archive's options.")
    system = sys.argv.pop(1)
    module = hindcast_hrrr if system == "hrrr" else hindcast_reforecast
    directory = get_settings().data_dir / "validation" / "weather" / system
    directory.mkdir(parents=True, exist_ok=True)
    with patch.object(module, "out_path", lambda region: directory / f"{region}.json"):
        module.main()


if __name__ == "__main__":
    main()
