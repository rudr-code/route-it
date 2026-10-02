# Route.it Project Rules & System Specification

## Project Goal
Route.it is an adaptive quantum-inspired fleet routing system for the Smart India Hackathon 2026 (PS SIH26137: Quantum-Inspired Intelligent Traffic Route Optimization Using Metaheuristic Optimization).
It solves the capacitated vehicle routing problem with time windows (CVRPTW) with time-dependent travel times, and re-optimises when traffic events happen.
"Quantum-inspired" means a CLASSICAL algorithm: Quantum-behaved Particle Swarm Optimization (QPSO, Sun, Feng & Xu 2004). No quantum hardware or quantum libraries.

## Architecture
- QPSO decides the order of customer stops. Valhalla (road router) finds the actual roads and travel times.
- Pipeline: input -> cost oracle (travel-time matrix) -> QPSO over random-key giant tour -> Prins Split into feasible routes -> local search (2-opt, relocate, swap) -> optimised routes + ETAs.
- Dynamic layer: event -> impact check (re-plan only if delta F > theta, with a stability penalty) -> Tier 1 path repair -> Tier 2 local repair -> Tier 3 QPSO warm start.
- MVP scope: single depot, one vehicle type. Multi-depot, SUMO, CO2 objective come only after MVP is complete.

## Repo Layout
```
/solver       # QPSO, PSO baseline, Split, local search, constraints
/routing      # Valhalla client, cost oracle, cache, traffic adapters
/dynamic      # Event simulator, impact check, tiered repair
/api          # FastAPI service + WebSocket
/dashboard    # React + MapLibre UI
/benchmarks   # Runners, instances, results, plots
/docs         # Design notes, benchmark report, demo script
/tests        # Mirrors the source folders
```

## Tech Stack
Python 3.11+, NumPy, Numba, OR-Tools (baseline only), FastAPI, Pydantic, pytest, OSMnx, Valhalla (Docker), React, MapLibre GL.

## Coding Standards
- Type hints everywhere. Docstrings on public functions. Small pure functions where possible.
- Every module ships with pytest tests. Never mark a task done if tests fail.
- All randomness takes an explicit seed so results are reproducible.
- Config in YAML or Pydantic settings, no magic numbers inside algorithms.
- Keep the solver independent of the API and dashboard. The solver must run from a CLI.

## Integrity Rules
- NEVER fabricate, hardcode, estimate, or "illustrate" benchmark results or performance numbers. Every number in docs or UI must come from a real run saved in `/benchmarks/results`.
- If OR-Tools beats our solver on an instance, report it honestly.
- Do not claim real live traffic unless a real provider is wired in. Simulated or time-of-day traffic must be labelled as simulated in UI and docs.
- Do not silently change an algorithm to make a test pass. Explain any deviation.

## Working Style
- In Planning mode, always produce an implementation plan artifact and wait for approval before coding.
- Prefer the simplest approach that works, then optimise with profiling evidence.
- After each task, summarise: what changed, how to run it, what is untested.
- If requirements are ambiguous, ask one concise question instead of guessing.
