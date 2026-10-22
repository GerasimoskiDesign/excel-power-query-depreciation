"""Static checks on the Power Query (M) scripts.

M cannot run outside Excel / Power BI, so these tests guard what *can* drift:
load order, the alias tables shared with Python, output column order, and a
few M pitfalls that only show up at refresh time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from depreciation_model.config import COLUMN_ALIASES, MOVEMENT_TYPE_ALIASES
from depreciation_model.schedule import AMOUNT_COLUMNS
from tests.conftest import REPO_ROOT

PQ_DIR = REPO_ROOT / "powerquery"
PQ_FILES = sorted(PQ_DIR.glob("*.pq"))


def _query_name(path: Path) -> str:
    m = re.search(r"^// Query name: (\w+)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"{path.name} has no '// Query name:' header"
    return m.group(1)


def _code(path: Path) -> str:
    """M source without // comments and string literals (for identifier scans)."""
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return re.sub(r'"(?:[^"]|"")*"', '""', text)


def _alias_pairs(path: Path) -> dict[str, str]:
    return dict(re.findall(r'\{"([^"]+)", "([^"]+)"\}', path.read_text(encoding="utf-8")))


def test_files_are_numbered_in_load_order_and_names_are_unique() -> None:
    assert len(PQ_FILES) == 14
    numbers = [int(p.name.split("_")[0]) for p in PQ_FILES]
    assert numbers == list(range(1, 15))
    names = [_query_name(p) for p in PQ_FILES]
    assert len(set(names)) == len(names)
    for p, name in zip(PQ_FILES, names, strict=True):
        assert p.stem.split("_", 1)[1] == name


def test_queries_only_reference_queries_loaded_before_them() -> None:
    names = [_query_name(p) for p in PQ_FILES]
    for i, p in enumerate(PQ_FILES):
        code = _code(p)
        for j, other in enumerate(names):
            if j != i and re.search(rf"\b{other}\b", code):
                assert j < i, f"{p.name} uses {other}, which is loaded later"


def test_column_aliases_match_python() -> None:
    assert _alias_pairs(PQ_DIR / "04_ColumnAliases.pq") == COLUMN_ALIASES


def test_movement_type_aliases_match_python() -> None:
    assert _alias_pairs(PQ_DIR / "05_MovementTypeAliases.pq") == MOVEMENT_TYPE_ALIASES


def test_monthly_totals_output_columns_match_expected_outputs() -> None:
    text = (PQ_DIR / "14_MonthlyTotals.pq").read_text(encoding="utf-8")
    listed = re.search(r"AmountColumns = \{(.*?)\}", text, re.DOTALL)
    assert listed
    assert re.findall(r'"(\w+)"', listed.group(1)) == AMOUNT_COLUMNS
    assert '{"month_start", "asset_rows"} & AmountColumns' in text
    header = (REPO_ROOT / "expected_outputs" / "monthly_totals.csv").read_text().splitlines()[0]
    assert header.split(",") == ["month_start", "asset_rows", *AMOUNT_COLUMNS]


@pytest.mark.parametrize("path", PQ_FILES, ids=lambda p: p.name)
def test_brackets_are_balanced(path: Path) -> None:
    code = _code(path)
    for open_, close in ("()", "[]", "{}"):
        assert code.count(open_) == code.count(close), f"{path.name}: {open_}{close} unbalanced"


@pytest.mark.parametrize("path", PQ_FILES, ids=lambda p: p.name)
def test_no_self_referencing_record_fields(path: Path) -> None:
    # Inside an M record literal "x = x" refers to the field itself -> cyclic reference.
    assert not re.search(r"\b(\w+) = \1\s*[,\]]", _code(path))


def test_depreciation_query_documents_the_same_convention_as_python() -> None:
    text = (PQ_DIR / "13_Depreciation.pq").read_text(encoding="utf-8")
    assert "(dimA - Date.Day(acquired) + 1) / dimA" in text  # first month incl. acquisition day
    assert "(Date.Day(disposed) - 1) / Date.DaysInMonth(disposed)" in text  # days before disposal
    assert "List.Min({cost, cost * ServiceMonths(acquired, disposed, k) / life})" in text
