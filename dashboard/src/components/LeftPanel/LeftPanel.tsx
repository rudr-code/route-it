import { useState } from 'react';
import { ConvergenceChart } from './ConvergenceChart';
import type { ConvergencePoint, SolverState } from '../../hooks/useSolver';
import type { SolveRequest } from '../../api/types';
import { vadodaraScenario } from '../../data/vadodara_scenario';

interface LeftPanelProps {
  solverState: SolverState;
  convergence: ConvergencePoint[];
  onLoadScenario: (scenario: typeof vadodaraScenario) => void;
  onSolve: (params: Partial<SolveRequest>) => void;
}

export function LeftPanel({ solverState, convergence, onLoadScenario, onSolve }: LeftPanelProps) {
  const [particles, setParticles] = useState(25);
  const [iters, setIters] = useState(60);
  const [seed, setSeed] = useState(42);
  const [oracle, setOracle] = useState<'euclidean' | 'valhalla'>('euclidean');

  const isRunning = solverState.isLoading && !!solverState.job;
  const hasProblem = !!solverState.problemId;

  const progressPct =
    solverState.job && solverState.job.max_iters > 0
      ? Math.round((solverState.job.progress_iteration / solverState.job.max_iters) * 100)
      : 0;

  return (
    <div className="left-panel glass-panel">
      {/* Header */}
      <div className="panel-header">
        <div className="logo-group">
          <span className="logo-icon">⚛</span>
          <span className="logo-text">Route<span className="logo-dot">.it</span></span>
        </div>
        <span className="panel-subtitle">Quantum-Inspired Fleet Routing</span>
      </div>

      {/* Scenario Section */}
      <div className="panel-section">
        <div className="section-label">Scenario</div>
        <button
          id="btn-load-scenario"
          className="btn btn-primary"
          onClick={() => onLoadScenario(vadodaraScenario)}
          disabled={isRunning}
        >
          <span>📍</span> Load Vadodara (30 stops)
        </button>
        {hasProblem && (
          <div className="status-chip loaded">
            <span className="chip-dot" /> {solverState.problemId}
          </div>
        )}
      </div>

      {/* Solver Settings */}
      <div className="panel-section">
        <div className="section-label">Solver Settings</div>

        <div className="settings-grid">
          <label className="setting-row">
            <span>Particles</span>
            <input
              id="input-particles"
              type="number"
              min={5}
              max={200}
              value={particles}
              onChange={(e) => setParticles(Number(e.target.value))}
              className="setting-input"
              disabled={isRunning}
            />
          </label>
          <label className="setting-row">
            <span>Iterations</span>
            <input
              id="input-iterations"
              type="number"
              min={5}
              max={1000}
              value={iters}
              onChange={(e) => setIters(Number(e.target.value))}
              className="setting-input"
              disabled={isRunning}
            />
          </label>
          <label className="setting-row">
            <span>Seed</span>
            <input
              id="input-seed"
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              className="setting-input"
              disabled={isRunning}
            />
          </label>
          <label className="setting-row">
            <span>Oracle</span>
            <select
              id="select-oracle"
              value={oracle}
              onChange={(e) => setOracle(e.target.value as 'euclidean' | 'valhalla')}
              className="setting-input setting-select"
              disabled={isRunning}
            >
              <option value="euclidean">Euclidean</option>
              <option value="valhalla">Valhalla</option>
            </select>
          </label>
        </div>
      </div>

      {/* Solve Button */}
      <div className="panel-section">
        <button
          id="btn-solve"
          className={`btn ${isRunning ? 'btn-running' : 'btn-solve'}`}
          disabled={!hasProblem || isRunning}
          onClick={() =>
            onSolve({
              num_particles: particles,
              max_iters: iters,
              seed,
              cost_oracle_type: oracle,
            })
          }
        >
          {isRunning ? (
            <>
              <span className="spinner-sm" />
              Solving… {progressPct}%
            </>
          ) : (
            <>
              <span>▶</span> Solve
            </>
          )}
        </button>

        {isRunning && (
          <div className="progress-bar-wrap">
            <div className="progress-bar" style={{ width: `${progressPct}%` }} />
          </div>
        )}

        {solverState.solution && !isRunning && (
          <div className="solve-result">
            <span className={`feasible-badge ${solverState.solution.is_feasible ? 'ok' : 'warn'}`}>
              {solverState.solution.is_feasible ? '✓ Feasible' : '⚠ Infeasible'}
            </span>
            <span className="result-cost">Cost: {solverState.solution.total_cost.toFixed(1)}</span>
            <span className="result-time">{solverState.solution.execution_time_sec.toFixed(2)}s</span>
          </div>
        )}
      </div>

      {/* Convergence Chart */}
      <div className="panel-section chart-section">
        <ConvergenceChart data={convergence} isRunning={isRunning} />
      </div>

      {/* Error */}
      {solverState.error && (
        <div className="error-box">
          <span>⚠</span> {solverState.error}
        </div>
      )}
    </div>
  );
}
