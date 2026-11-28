"""Compatibility launcher. Preferred entry: python -m ultron."""
from ultron.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
