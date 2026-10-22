"""Allow ``python -m depreciation_model <command>``."""

from depreciation_model.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
