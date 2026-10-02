"""Instance verification utility for Route.it benchmarks.

Scans the benchmarks/instances directory, verifies presence of recommended
benchmark files (CVRPLIB X-instances and Solomon instances), and validates
that all present files parse correctly without schema errors.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence

# Ensure project root is in sys.path when executed directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from solver.io import load_cvrplib, load_solomon


@dataclass
class CheckResult:
    """Status result for a single benchmark instance file."""

    filename: str
    category: str
    exists: bool
    parsed: bool
    num_customers: int | None = None
    num_vehicles: int | None = None
    capacity: float | None = None
    error: str | None = None


RECOMMENDED_INSTANCES: list[tuple[str, str]] = [
    # Reference fixture
    ("A-n32-k5.vrp", "CVRPLIB (Ref)"),
    # 5 Small CVRPLIB X-instances (Uchoa et al., 2017)
    ("X-n101-k25.vrp", "CVRPLIB-X"),
    ("X-n106-k14.vrp", "CVRPLIB-X"),
    ("X-n110-k9.vrp", "CVRPLIB-X"),
    ("X-n115-k10.vrp", "CVRPLIB-X"),
    ("X-n120-k6.vrp", "CVRPLIB-X"),
    # 6 Solomon CVRPTW instances (Solomon, 1987)
    ("C101.txt", "Solomon Clustered"),
    ("C201.txt", "Solomon Clustered"),
    ("R101.txt", "Solomon Random"),
    ("R201.txt", "Solomon Random"),
    ("RC101.txt", "Solomon Mixed"),
    ("RC201.txt", "Solomon Mixed"),
]


def verify_instance(file_path: Path, category: str = "Unknown") -> CheckResult:
    """Verify existence and parse validity of a single benchmark file."""
    if not file_path.is_file():
        return CheckResult(
            filename=file_path.name,
            category=category,
            exists=False,
            parsed=False,
            error="File missing",
        )

    try:
        if file_path.suffix.lower() == ".txt":
            problem = load_solomon(file_path)
        elif file_path.suffix.lower() == ".vrp":
            problem = load_cvrplib(file_path)
        else:
            return CheckResult(
                filename=file_path.name,
                category=category,
                exists=True,
                parsed=False,
                error=f"Unsupported extension: {file_path.suffix}",
            )

        cap = problem.vehicles[0].capacity if problem.vehicles else None
        return CheckResult(
            filename=file_path.name,
            category=category,
            exists=True,
            parsed=True,
            num_customers=problem.num_customers,
            num_vehicles=problem.num_vehicles,
            capacity=cap,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            filename=file_path.name,
            category=category,
            exists=True,
            parsed=False,
            error=str(exc),
        )


def check_all_instances(instances_dir: Path) -> list[CheckResult]:
    """Check all recommended target instances and any extra files in instances_dir."""
    results: list[CheckResult] = []
    checked_files: set[str] = set()

    # 1. Check recommended target instances
    for filename, category in RECOMMENDED_INSTANCES:
        path = instances_dir / filename
        results.append(verify_instance(path, category))
        checked_files.add(filename.lower())

    # 2. Check any extra files present in the directory
    if instances_dir.is_dir():
        for p in sorted(instances_dir.iterdir()):
            if p.is_file() and p.name.lower() not in checked_files and p.suffix in (".vrp", ".txt"):
                cat = "Solomon (Extra)" if p.suffix == ".txt" else "CVRPLIB (Extra)"
                results.append(verify_instance(p, cat))

    return results


def print_report(results: list[CheckResult]) -> None:
    """Format and print an aligned summary table of verification results."""
    header = (
        f"{'Instance':<18} {'Type':<18} {'Found':<7} {'Parsed':<8} "
        f"{'Cust':<6} {'Veh':<6} {'Capacity':<10} {'Details'}"
    )
    separator = "-" * len(header)
    print(separator)
    print(header)
    print(separator)

    found_count = 0
    parsed_count = 0

    for r in results:
        found_str = "YES" if r.exists else "NO"
        parsed_str = "YES" if r.parsed else "NO"
        cust_str = str(r.num_customers) if r.num_customers is not None else "-"
        veh_str = str(r.num_vehicles) if r.num_vehicles is not None else "-"
        cap_str = f"{r.capacity:.1f}" if r.capacity is not None else "-"
        details = r.error or "OK"

        if r.exists:
            found_count += 1
        if r.parsed:
            parsed_count += 1

        print(
            f"{r.filename:<18} {r.category:<18} {found_str:<7} {parsed_str:<8} "
            f"{cust_str:<6} {veh_str:<6} {cap_str:<10} {details}"
        )

    print(separator)
    total_target = len(RECOMMENDED_INSTANCES)
    print(f"Summary: {found_count}/{total_target} recommended instances found | {parsed_count} parsed successfully.")
    print(separator)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Verify presence and parsing of Route.it benchmark instances."
    )
    parser.add_argument(
        "--instances-dir",
        type=Path,
        default=project_root / "benchmarks" / "instances",
        help="Path to benchmark instances directory (default: benchmarks/instances)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero exit code if any recommended instance is missing or unparsed.",
    )
    args = parser.parse_args(argv)

    results = check_all_instances(args.instances_dir)
    print_report(results)

    # In strict mode, fail if any recommended instance is missing or fails to parse
    if args.strict:
        for r in results:
            if not r.exists or not r.parsed:
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
