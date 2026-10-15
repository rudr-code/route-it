"""Storage layer interface and thread-safe in-memory implementation for Route.it API.

Enables full decoupling of API handlers from storage persistence.
Swappable to SQLite / persistent database without altering route logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import threading
from typing import TYPE_CHECKING

from api.models import SolveJob
from solver.models import Problem, Solution

if TYPE_CHECKING:
    from dynamic.reoptimizer import ReoptimizationRecord
    from routing.cost_oracle import CostOracle


class ProblemStore(ABC):
    """Abstract interface defining required storage operations for Route.it."""

    @abstractmethod
    def save_problem(self, problem: Problem) -> None:
        """Store or update a problem instance."""
        ...

    @abstractmethod
    def get_problem(self, problem_id: str) -> Problem | None:
        """Retrieve a problem instance by ID."""
        ...

    @abstractmethod
    def list_problems(self) -> list[Problem]:
        """List all stored problem instances."""
        ...

    @abstractmethod
    def delete_problem(self, problem_id: str) -> bool:
        """Delete a problem instance and its associated solutions/jobs."""
        ...

    @abstractmethod
    def save_solution(self, problem_id: str, solution: Solution) -> None:
        """Store or update the active fleet solution for a problem."""
        ...

    @abstractmethod
    def get_solution(self, problem_id: str) -> Solution | None:
        """Retrieve the active fleet solution for a problem."""
        ...

    @abstractmethod
    def save_job(self, job: SolveJob) -> None:
        """Store or update optimization job status."""
        ...

    @abstractmethod
    def get_job(self, job_id: str) -> SolveJob | None:
        """Retrieve job by its unique identifier."""
        ...

    @abstractmethod
    def add_event_record(self, problem_id: str, record: ReoptimizationRecord) -> None:
        """Append an audit record from a re-optimization event."""
        ...

    @abstractmethod
    def get_event_records(self, problem_id: str) -> list[ReoptimizationRecord]:
        """Retrieve the chronological audit history for a problem."""
        ...

    @abstractmethod
    def save_oracle(self, problem_id: str, oracle: CostOracle) -> None:
        """Cache the active cost oracle instance associated with a problem."""
        ...

    @abstractmethod
    def get_oracle(self, problem_id: str) -> CostOracle | None:
        """Retrieve the cached cost oracle instance associated with a problem."""
        ...


class InMemoryProblemStore(ProblemStore):
    """Thread-safe in-memory implementation of ProblemStore."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._problems: dict[str, Problem] = {}
        self._solutions: dict[str, Solution] = {}
        self._jobs: dict[str, SolveJob] = {}
        self._event_records: dict[str, list[ReoptimizationRecord]] = {}
        self._oracles: dict[str, CostOracle] = {}

    def save_problem(self, problem: Problem) -> None:
        with self._lock:
            self._problems[problem.id] = problem

    def get_problem(self, problem_id: str) -> Problem | None:
        with self._lock:
            return self._problems.get(problem_id)

    def list_problems(self) -> list[Problem]:
        with self._lock:
            return list(self._problems.values())

    def delete_problem(self, problem_id: str) -> bool:
        with self._lock:
            if problem_id not in self._problems:
                return False
            del self._problems[problem_id]
            self._solutions.pop(problem_id, None)
            self._event_records.pop(problem_id, None)
            self._oracles.pop(problem_id, None)
            # Remove associated jobs
            job_ids_to_del = [j_id for j_id, job in self._jobs.items() if job.problem_id == problem_id]
            for j_id in job_ids_to_del:
                del self._jobs[j_id]
            return True

    def save_solution(self, problem_id: str, solution: Solution) -> None:
        with self._lock:
            self._solutions[problem_id] = solution

    def get_solution(self, problem_id: str) -> Solution | None:
        with self._lock:
            return self._solutions.get(problem_id)

    def save_job(self, job: SolveJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> SolveJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def add_event_record(self, problem_id: str, record: ReoptimizationRecord) -> None:
        with self._lock:
            self._event_records.setdefault(problem_id, []).append(record)

    def get_event_records(self, problem_id: str) -> list[ReoptimizationRecord]:
        with self._lock:
            return list(self._event_records.get(problem_id, []))

    def save_oracle(self, problem_id: str, oracle: CostOracle) -> None:
        with self._lock:
            self._oracles[problem_id] = oracle

    def get_oracle(self, problem_id: str) -> CostOracle | None:
        with self._lock:
            return self._oracles.get(problem_id)

    def clear(self) -> None:
        """Clear all stored state (primarily for test resets)."""
        with self._lock:
            self._problems.clear()
            self._solutions.clear()
            self._jobs.clear()
            self._event_records.clear()
            self._oracles.clear()


# Global store instance for FastAPI dependency injection
_global_store: ProblemStore = InMemoryProblemStore()


def get_store() -> ProblemStore:
    """FastAPI dependency for accessing the active ProblemStore."""
    return _global_store


def set_store(store: ProblemStore) -> None:
    """Override active store (e.g. for testing or SQLite backend swap)."""
    global _global_store
    _global_store = store
