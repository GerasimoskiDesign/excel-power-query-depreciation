"""Clean and combine the monthly movement files.

Mirrors ``powerquery/06_fnCleanMovementFile.pq`` step by step. The rules are
deliberately strict: an unknown header or movement type stops the run instead
of being silently dropped, because a silently dropped disposal would keep an
asset depreciating for months - the classic error in hand-built workbooks.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from depreciation_model.config import COLUMN_ALIASES, MOVEMENT_COLUMNS, MOVEMENT_TYPE_ALIASES

log = logging.getLogger(__name__)

BOM = "\ufeff"


class SourceFileError(ValueError):
    """A movement file cannot be interpreted safely."""


def _is_blank(cells: list[str]) -> bool:
    return all(c.strip() == "" for c in cells)


def normalise_header(text: str) -> str:
    """Header key used for alias lookup: no BOM, trimmed, lower case."""
    return text.replace(BOM, "").strip().lower()


def parse_number(text: str | None) -> float | None:
    """Parse numbers exported as text, e.g. ``"1,234.50 "``.

    Thousands separators and spaces are removed; the decimal point is always
    ``.`` in these exports (documented assumption, see docs/CONVENTIONS.md).
    """
    if text is None:
        return None
    cleaned = text.replace(",", "").replace(" ", "").strip()
    return float(cleaned) if cleaned else None


def parse_date(text: str | None) -> date | None:
    """Accept ISO ``YYYY-MM-DD`` and day-first ``DD/MM/YYYY`` - the two formats seen in exports."""
    if text is None or text.strip() == "":
        return None
    s = text.strip()
    if "/" in s:
        day, month, year = s.split("/")
        return date(int(year), int(month), int(day))
    year, month, day = s[:10].split("-")
    return date(int(year), int(month), int(day))


def clean_movement_file(content: bytes, source_file: str) -> pd.DataFrame:
    """Turn one raw monthly export into the canonical movement table."""
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))

    # 1. Skip blank rows above the header (exports padded with empty lines).
    while rows and _is_blank(rows[0]):
        rows.pop(0)
    if not rows:
        raise SourceFileError(f"{source_file}: file has no header row")

    # 2. Promote headers and map every known alias to the canonical name.
    header = [normalise_header(h) for h in rows[0]]
    mapping: dict[int, str] = {}
    for pos, h in enumerate(header):
        if h in COLUMN_ALIASES:
            mapping[pos] = COLUMN_ALIASES[h]
        elif h:
            raise SourceFileError(f"{source_file}: unknown column header '{rows[0][pos]}'")
    if len(set(mapping.values())) != len(mapping):
        raise SourceFileError(f"{source_file}: two headers map to the same column")
    missing = set(MOVEMENT_COLUMNS) - set(mapping.values())
    if missing:
        raise SourceFileError(f"{source_file}: missing columns {sorted(missing)}")

    # 3. Drop blank rows anywhere in the body.
    body = [raw for raw in rows[1:] if not _is_blank(raw)]

    # 4. Standardise values (plain Python, so missing values stay None rather than NaN).
    records = []
    for raw in body:
        cell = {col: (raw[p] if p < len(raw) else "") for p, col in mapping.items()}
        mtype = cell["movement_type"].strip().lower()
        if mtype not in MOVEMENT_TYPE_ALIASES:
            raise SourceFileError(f"{source_file}: unknown movement type '{mtype}'")
        life = parse_number(cell["useful_life_months"])
        records.append(
            {
                "asset_id": cell["asset_id"].strip().upper(),
                "movement_type": MOVEMENT_TYPE_ALIASES[mtype],
                "movement_date": parse_date(cell["movement_date"]),
                "amount": parse_number(cell["amount"]),
                "asset_name": _text_or_none(cell["asset_name"]),
                "category": _text_or_none(cell["category"]),
                "useful_life_months": None if life is None else int(life),
                "cost_centre": _text_or_none(cell["cost_centre"]),
                "source_file": source_file,
            }
        )
    return pd.DataFrame(records, columns=[*MOVEMENT_COLUMNS, "source_file"], dtype=object)


def _text_or_none(s: str) -> str | None:
    s = s.strip()
    return s or None


def load_movements(movements_dir: Path) -> pd.DataFrame:
    """Clean every ``*.csv`` in the folder and stack them (file name order)."""
    # Same filter as 08_MovementsClean.pq: CSVs only, no Excel lock files.
    files = sorted(f for f in movements_dir.glob("*.csv") if not f.name.startswith("~"))
    if not files:
        raise SourceFileError(f"No movement files found in {movements_dir}")
    frames = [clean_movement_file(f.read_bytes(), f.name) for f in files]
    combined = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    log.info("Cleaned %d movement rows from %d files", len(combined), len(files))
    return combined


def load_register(register_file: Path) -> pd.DataFrame:
    """Read the opening register (a clean system extract) with proper types."""
    df = pd.read_csv(register_file, dtype=str, keep_default_na=False)
    out = pd.DataFrame(
        {
            "asset_id": df["asset_id"].str.strip().str.upper(),
            "asset_name": df["asset_name"].str.strip(),
            "category": df["category"].str.strip(),
            "cost_centre": df["cost_centre"].str.strip(),
            "acquisition_date": df["acquisition_date"].map(parse_date),
            "cost": df["cost"].map(parse_number),
            "useful_life_months": df["useful_life_months"].map(lambda s: int(parse_number(s))),
            "disposal_date": df["disposal_date"].map(parse_date),
        }
    )
    return out.astype(object).where(out.notna(), None)
