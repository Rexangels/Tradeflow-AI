#!/usr/bin/env python
from pathlib import Path
import os
import sys

_VENV_SITE_PACKAGES = Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages"
if _VENV_SITE_PACKAGES.exists() and str(_VENV_SITE_PACKAGES) not in sys.path:
    sys.path.append(str(_VENV_SITE_PACKAGES))


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tradeflow_api.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Couldn't import Django. Did you install the backend requirements?") from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
