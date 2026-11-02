"""Benchmark and data loader/saver utilities for Route.it.

Supports:
- Solomon (1987) CVRPTW .txt benchmark instances
- CVRPLIB TSPLIB-style .vrp benchmark instances
- JSON serialization/deserialization for Problem and Solution
"""

from __future__ import annotations

import math
from pathlib import Path
import re

from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle


def load_solomon(file_path: str | Path) -> Problem:
    """Parse a standard Solomon (1987) CVRPTW benchmark text file.

    Args:
        file_path: Path to the Solomon .txt instance file.

    Returns:
        Fully initialized Problem instance with computed Euclidean matrices.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Solomon instance not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    instance_name = lines[0] if lines else path.stem
    num_vehicles: int | None = None
    capacity: float | None = None

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("VEHICLE"):
            idx += 1
            # Next line usually has headers (NUMBER CAPACITY) or the values
            parts = lines[idx].split()
            if parts and parts[0].isdigit():
                num_vehicles = int(parts[0])
                capacity = float(parts[1])
            else:
                idx += 1
                parts = lines[idx].split()
                num_vehicles = int(parts[0])
                capacity = float(parts[1])
            break
        idx += 1

    if num_vehicles is None or capacity is None:
        raise ValueError(f"Could not parse VEHICLE section in {path}")

    # Find CUSTOMER section
    while idx < len(lines) and not lines[idx].startswith("CUSTOMER"):
        idx += 1

    # Skip header line (CUST NO. XCOORD ...)
    idx += 1
    while idx < len(lines):
        first_token = lines[idx].split()[0]
        if first_token.isdigit():
            break
        idx += 1

    depot: Depot | None = None
    customers: list[Customer] = []

    for line in lines[idx:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        cust_id = parts[0]
        x = float(parts[1])
        y = float(parts[2])
        demand = float(parts[3])
        ready_time = float(parts[4])
        due_time = float(parts[5])
        service_time = float(parts[6])

        if cust_id == "0":
            depot = Depot(
                id="depot",
                lat=y,
                lon=x,
                ready_time=ready_time,
                due_time=due_time,
                service_time=service_time,
            )
        else:
            customers.append(
                Customer(
                    id=cust_id,
                    lat=y,
                    lon=x,
                    demand=demand,
                    ready_time=ready_time,
                    due_time=due_time,
                    service_time=service_time,
                )
            )

    if depot is None:
        raise ValueError(f"Depot (customer 0) was not found in {path}")

    vehicles = [
        Vehicle(
            id=f"V_{i+1}",
            capacity=capacity,
            shift_start=depot.ready_time,
            shift_end=depot.due_time,
        )
        for i in range(num_vehicles)
    ]

    problem = Problem(
        id=instance_name,
        depot=depot,
        customers=customers,
        vehicles=vehicles,
        coordinate_system="planar",
    )
    problem.compute_euclidean_matrices(speed=1.0)
    return problem


def load_cvrplib(file_path: str | Path) -> Problem:
    """Parse a standard CVRPLIB / TSPLIB .vrp file.

    Extracts coordinates, demands, capacity, depot, and vehicle count.
    Default time windows and service times are applied since CVRP has no windows.

    Args:
        file_path: Path to the .vrp file.

    Returns:
        Problem instance with computed Euclidean matrices.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"CVRPLIB instance not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    name = path.stem
    comment = ""
    capacity: float | None = None
    dimension: int | None = None
    node_coords: dict[int, tuple[float, float]] = {}
    demands: dict[int, float] = {}
    depot_node_id: int = 1

    section = ""
    for line in lines:
        if line.startswith("NAME"):
            name = line.split(":", 1)[1].strip() if ":" in line else line.split()[1]
        elif line.startswith("COMMENT"):
            comment = line.split(":", 1)[1].strip() if ":" in line else line
        elif line.startswith("CAPACITY"):
            capacity = float(line.split(":", 1)[1].strip() if ":" in line else line.split()[1])
        elif line.startswith("DIMENSION"):
            dimension = int(line.split(":", 1)[1].strip() if ":" in line else line.split()[1])
        elif line.startswith("NODE_COORD_SECTION"):
            section = "NODE_COORD_SECTION"
            continue
        elif line.startswith("DEMAND_SECTION"):
            section = "DEMAND_SECTION"
            continue
        elif line.startswith("DEPOT_SECTION"):
            section = "DEPOT_SECTION"
            continue
        elif line.startswith("EOF"):
            break
        elif section == "NODE_COORD_SECTION":
            parts = line.split()
            if len(parts) >= 3:
                node_coords[int(parts[0])] = (float(parts[1]), float(parts[2]))
        elif section == "DEMAND_SECTION":
            parts = line.split()
            if len(parts) >= 2:
                demands[int(parts[0])] = float(parts[1])
        elif section == "DEPOT_SECTION":
            parts = line.split()
            if parts and parts[0] != "-1":
                depot_node_id = int(parts[0])

    if capacity is None:
        raise ValueError(f"CAPACITY header missing in {path}")
    if not node_coords:
        raise ValueError(f"No coordinates found in {path}")

    # Determine number of vehicles from name or comment (e.g. A-n32-k5 -> 5 vehicles)
    num_vehicles: int | None = None
    k_match = re.search(r"-k(\d+)", name, re.IGNORECASE)
    if k_match:
        num_vehicles = int(k_match.group(1))
    else:
        truck_match = re.search(r"trucks?\s*:\s*(\d+)", comment, re.IGNORECASE)
        if truck_match:
            num_vehicles = int(truck_match.group(1))

    total_demand = sum(demands.values())
    if num_vehicles is None:
        num_vehicles = max(1, math.ceil(total_demand / capacity))

    depot_x, depot_y = node_coords[depot_node_id]
    depot = Depot(
        id="depot",
        lat=depot_y,
        lon=depot_x,
        ready_time=0.0,
        due_time=1e7,
        service_time=0.0,
    )

    customers: list[Customer] = []
    for node_id, (x, y) in sorted(node_coords.items()):
        if node_id == depot_node_id:
            continue
        customers.append(
            Customer(
                id=str(node_id),
                lat=y,
                lon=x,
                demand=demands.get(node_id, 0.0),
                ready_time=0.0,
                due_time=1e7,
                service_time=0.0,
            )
        )

    vehicles = [
        Vehicle(
            id=f"V_{i+1}",
            capacity=capacity,
            shift_start=0.0,
            shift_end=1e7,
        )
        for i in range(num_vehicles)
    ]

    problem = Problem(
        id=name,
        depot=depot,
        customers=customers,
        vehicles=vehicles,
        coordinate_system="planar",
    )
    problem.compute_euclidean_matrices(speed=1.0)
    return problem


def save_problem_json(problem: Problem, file_path: str | Path) -> None:
    """Serialize a Problem instance to a JSON file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(problem.model_dump_json(indent=2))


def load_problem_json(file_path: str | Path) -> Problem:
    """Deserialize a Problem instance from a JSON file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Problem file not found at {path}")
    with path.open("r", encoding="utf-8") as f:
        return Problem.model_validate_json(f.read())


def save_solution_json(solution: Solution, file_path: str | Path) -> None:
    """Serialize a Solution instance to a JSON file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(solution.model_dump_json(indent=2))


def load_solution_json(file_path: str | Path) -> Solution:
    """Deserialize a Solution instance from a JSON file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Solution file not found at {path}")
    with path.open("r", encoding="utf-8") as f:
        return Solution.model_validate_json(f.read())
