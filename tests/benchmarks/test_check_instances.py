"""Unit tests for benchmark instance verification script in benchmarks/check_instances.py."""

from pathlib import Path
import pytest

from benchmarks.check_instances import (
    RECOMMENDED_INSTANCES,
    check_all_instances,
    main,
    verify_instance,
)


def test_verify_existing_reference_instance() -> None:
    """Test verify_instance on the included A-n32-k5.vrp reference file."""
    ref_path = Path("benchmarks/instances/A-n32-k5.vrp")
    result = verify_instance(ref_path, category="CVRPLIB")

    assert result.exists is True
    assert result.parsed is True
    assert result.num_customers == 31
    assert result.num_vehicles == 5
    assert result.capacity == 100.0
    assert result.error is None


def test_verify_missing_instance() -> None:
    """Test verify_instance on a non-existent file."""
    missing_path = Path("benchmarks/instances/non_existent.vrp")
    result = verify_instance(missing_path, category="Test")

    assert result.exists is False
    assert result.parsed is False
    assert result.error == "File missing"


def test_verify_unsupported_extension(tmp_path: Path) -> None:
    """Test verify_instance on an unsupported extension like .csv."""
    unsupported = tmp_path / "dummy.csv"
    unsupported.write_text("a,b,c", encoding="utf-8")

    result = verify_instance(unsupported, category="Other")
    assert result.exists is True
    assert result.parsed is False
    assert "Unsupported extension" in (result.error or "")


def test_check_all_instances_covers_recommended() -> None:
    """Test that check_all_instances includes all recommended benchmark targets."""
    instances_dir = Path("benchmarks/instances")
    results = check_all_instances(instances_dir)

    filenames = [r.filename for r in results]
    for target, _ in RECOMMENDED_INSTANCES:
        assert target in filenames


def test_cli_main_non_strict() -> None:
    """Test main() CLI runs successfully in normal (non-strict) mode."""
    exit_code = main(["--instances-dir", "benchmarks/instances"])
    assert exit_code == 0


def test_cli_main_strict_fails_when_files_missing() -> None:
    """Test main() CLI fails with code 1 in strict mode when files are missing."""
    exit_code = main(["--instances-dir", "benchmarks/instances", "--strict"])
    assert exit_code == 1
