"""Smoke tests for Route.it to ensure CI passes and environments are sane."""

import sys


def test_python_version() -> None:
    """Verify that Python runtime meets the minimum >= 3.11 requirement."""
    assert sys.version_info >= (3, 11), f"Requires Python >= 3.11, running {sys.version}"


def test_package_imports() -> None:
    """Verify that all core Route.it packages can be imported cleanly."""
    import api
    import benchmarks
    import dynamic
    import routing
    import solver

    assert solver.__version__ == "0.1.0"
    assert routing.__version__ == "0.1.0"
    assert dynamic.__version__ == "0.1.0"
    assert api.__version__ == "0.1.0"
    assert benchmarks.__version__ == "0.1.0"


def test_basic_arithmetic_sanity() -> None:
    """Basic sanity check ensuring test runner functions properly."""
    assert 1 + 1 == 2
