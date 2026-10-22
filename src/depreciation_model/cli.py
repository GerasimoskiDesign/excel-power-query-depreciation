"""Command line: ``python -m depreciation_model <command>``.

Commands
--------
generate   write synthetic source files (register + monthly movement files)
compute    run the Python reference model -> expected_outputs/ and powerbi/data/
workbook   build depreciation_model.xlsx (source tables, expected totals, Check sheet)
charts     write README charts to docs/img/
all        generate + compute + workbook + charts
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from depreciation_model.config import (
    DEFAULT_REPORT_MONTHS,
    Paths,
    default_seed,
    load_env,
)
from depreciation_model.dates import add_months, parse_month, report_months

log = logging.getLogger("depreciation_model")

DEFAULT_AS_OF = "2025-12"


def _window(as_of: str, n_months: int) -> list[date]:
    """Reporting months ending with the ``--as-of`` month (inclusive)."""
    start = add_months(parse_month(as_of), -(n_months - 1))
    return report_months(start, n_months)


def cmd_generate(args: argparse.Namespace, paths: Paths) -> None:
    from depreciation_model.generate import generate, write_source_files

    months = _window(args.as_of, args.months)
    data = generate(seed=args.seed, report_start=months[0], n_months=args.months)
    write_source_files(data, paths.source_dir, seed=args.seed)


def cmd_compute(args: argparse.Namespace, paths: Paths) -> None:
    from depreciation_model.pipeline import run_model
    from depreciation_model.reporting import (
        star_schema,
        write_expected_outputs,
        write_star_schema,
    )

    result = run_model(paths, _window(args.as_of, args.months))
    write_expected_outputs(result.schedule, paths.expected_dir)
    write_star_schema(star_schema(result.schedule, result.master, result.months), paths.powerbi_dir)


def cmd_workbook(args: argparse.Namespace, paths: Paths) -> None:
    from depreciation_model.pipeline import run_model
    from depreciation_model.reporting import monthly_totals
    from depreciation_model.workbook import PLACEHOLDER_FOLDER, build_workbook

    months = _window(args.as_of, args.months)
    result = run_model(paths, months)
    build_workbook(
        paths.workbook_file,
        result.register,
        result.movements,
        monthly_totals(result.schedule),
        months[0],
        len(months),
        source_folder=str(Path(args.source_folder).resolve())
        if args.source_folder
        else PLACEHOLDER_FOLDER,
    )


def cmd_charts(args: argparse.Namespace, paths: Paths) -> None:
    from depreciation_model.charts import write_charts
    from depreciation_model.pipeline import run_model

    result = run_model(paths, _window(args.as_of, args.months))
    write_charts(result.schedule, paths.img_dir)


def cmd_all(args: argparse.Namespace, paths: Paths) -> None:
    for step in (cmd_generate, cmd_compute, cmd_workbook, cmd_charts):
        step(args, paths)


COMMANDS = {
    "generate": cmd_generate,
    "compute": cmd_compute,
    "workbook": cmd_workbook,
    "charts": cmd_charts,
    "all": cmd_all,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m depreciation_model",
        description="Intangible-asset depreciation model (Python reference implementation).",
    )
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--seed", type=int, default=None, help="random seed (default 42)")
    parser.add_argument(
        "--as-of",
        default=DEFAULT_AS_OF,
        help="last reporting month, YYYY-MM (default %(default)s)",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=DEFAULT_REPORT_MONTHS,
        help="number of reporting months (default %(default)s)",
    )
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="repository root (default: cwd)"
    )
    parser.add_argument(
        "--source-folder",
        default=None,
        help="workbook only: folder written (as a full path) to the SourceFolder parameter",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    load_env()
    if args.seed is None:
        args.seed = default_seed()
    paths = Paths(root=args.root.resolve())
    COMMANDS[args.command](args, paths)
    log.info("Done: %s", args.command)
    return 0
