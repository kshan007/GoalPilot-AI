import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  TrendingUp,
  ArrowRight,
  RotateCcw,
  ShieldAlert,
  Info,
  Layers,
  ChevronDown,
  ChevronUp,
  FileText,
  Calendar,
  DollarSign,
  PieChart
} from 'lucide-react';

export default function ResultsDashboard({ result, onReset, onModifyInputs, onSelectBenchmark }) {
  const [showFullSchedule, setShowFullSchedule] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');

  if (!result) return null;

  const {
    status,
    message,
    user_id,
    is_benchmark_case,
    financial_summary,
    goal_summary,
    metrics,
    monthly_schedule = [],
    explanation,
    warnings = [],
    assumptions = []
  } = result;

  const isSuccess = metrics.is_goal_achieved;
  const isDeficit = status === 'deficit_infeasible';
  const fundingPct = metrics.funding_percentage;

  // Compute total dynamic income & dynamic surplus over horizon
  const totalSimulatedIncome = monthly_schedule.reduce((acc, curr) => acc + curr.income_dynamic, 0);
  const totalAllocated = metrics.optimized_goal_funding;
  const totalResidual = metrics.total_positive_cash_flow - totalAllocated;

  // Benchmark users for quick demonstration
  const benchmarkPresetIds = [
    { id: 'USER_00001', label: 'USER_00001 (Success 48m, ₹1.15L)' },
    { id: 'USER_00002', label: 'USER_00002 (Deficit Infeasible 51m)' },
    { id: 'USER_00003', label: 'USER_00003 (Success 46m, ₹99.8K)' },
    { id: 'USER_00004', label: 'USER_00004 (Success 60m, ₹75.4K)' },
    { id: 'USER_00005', label: 'USER_00005 (Affluent 120m, ₹2.06L)' },
    { id: 'USER_00008', label: 'USER_00008 (Stress Shortfall 11m)' },
    { id: 'USER_00010', label: 'USER_00010 (Success 24m, ₹96.7K)' }
  ];

  return (
    <div style={{ maxWidth: 1040, margin: '0 auto' }}>
      {/* Header Result Banner */}
      <div
        className="card"
        style={{
          borderLeftWidth: 6,
          borderLeftColor: isSuccess
            ? 'var(--accent-emerald)'
            : isDeficit
            ? 'var(--accent-rose)'
            : 'var(--accent-amber)',
          marginBottom: 24
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {isSuccess ? (
              <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--accent-emerald-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-emerald)' }}>
                <CheckCircle2 size={24} />
              </div>
            ) : isDeficit ? (
              <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--accent-rose-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-rose)' }}>
                <XCircle size={24} />
              </div>
            ) : (
              <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--accent-amber-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-amber)' }}>
                <AlertTriangle size={24} />
              </div>
            )}

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <h2 style={{ fontSize: 20, fontWeight: 700 }}>
                  {isSuccess
                    ? 'Goal Fully Achievable & Optimized'
                    : isDeficit
                    ? 'Structural Deficit — Optimization Infeasible'
                    : 'Partial Goal Funding — Shortfall Projected'}
                </h2>
                {is_benchmark_case && (
                  <span className="badge badge-cyan">Research Benchmark: {user_id}</span>
                )}
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                {message}
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-secondary btn-sm" onClick={onModifyInputs}>
              Modify Inputs
            </button>
            <button className="btn btn-outline-emerald btn-sm" onClick={onReset}>
              <RotateCcw size={14} /> New Plan
            </button>
          </div>
        </div>

        {/* Progress Bar */}
        <div style={{ marginTop: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6, fontWeight: 600 }}>
            <span style={{ color: 'var(--text-muted)' }}>Goal Achievement Progress</span>
            <span style={{ color: isSuccess ? 'var(--accent-emerald)' : 'var(--accent-amber)' }}>
              {fundingPct.toFixed(1)}% Funded (₹{totalAllocated.toLocaleString('en-IN')} of ₹{metrics.target_amount.toLocaleString('en-IN')})
            </span>
          </div>
          <div className="progress-container">
            <div
              className={`progress-fill ${!isSuccess ? 'warning' : ''}`}
              style={{ width: `${Math.min(100, Math.max(2, fundingPct))}%` }}
            />
          </div>
        </div>
      </div>

      {/* 4-Metric Grid */}
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-label">Goal Target</span>
          <span className="metric-value">₹{metrics.target_amount.toLocaleString('en-IN')}</span>
          <span className="metric-sub">{goal_summary.goal_name} ({metrics.goal_horizon_months}m)</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Optimized Funding</span>
          <span className="metric-value" style={{ color: isSuccess ? 'var(--accent-emerald)' : 'var(--accent-cyan)' }}>
            ₹{totalAllocated.toLocaleString('en-IN')}
          </span>
          <span className="metric-sub">{fundingPct.toFixed(1)}% of Target</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Projected Shortfall</span>
          <span className="metric-value" style={{ color: metrics.optimized_shortfall > 0 ? 'var(--accent-rose)' : 'var(--accent-emerald)' }}>
            ₹{metrics.optimized_shortfall.toLocaleString('en-IN')}
          </span>
          <span className="metric-sub">{metrics.optimized_shortfall === 0 ? 'Zero Deficit' : 'Unfunded Balance'}</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Available Surplus</span>
          <span className="metric-value">₹{metrics.total_positive_cash_flow.toLocaleString('en-IN')}</span>
          <span className="metric-sub">{metrics.goal_horizon_months}-Month Cash Boundary</span>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 10, borderBottom: '1px solid var(--border-subtle)', marginBottom: 24 }}>
        <button
          className={`btn btn-sm ${activeTab === 'overview' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('overview')}
        >
          Plan Overview & Why This Plan?
        </button>
        <button
          className={`btn btn-sm ${activeTab === 'schedule' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('schedule')}
        >
          Monthly Allocation Schedule ({monthly_schedule.length} Months)
        </button>
        <button
          className={`btn btn-sm ${activeTab === 'benchmarks' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('benchmarks')}
        >
          Research Benchmarks & Parity Audit
        </button>
      </div>

      {/* TAB 1: OVERVIEW & EXPLANATIONS */}
      {activeTab === 'overview' && (
        <div>
          {/* Financial Breakdown & Cash Allocation Summary */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20, marginBottom: 24 }}>
            {/* Financial Summary */}
            <div className="card">
              <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <DollarSign size={16} color="var(--accent-emerald)" /> Financial Baseline
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Gross Monthly Income</span>
                  <strong>₹{financial_summary.annual_income / 12}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Monthly Living Expenses</span>
                  <strong>₹{financial_summary.annual_expenditure / 12}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Debt-to-Income (EMI Ratio)</span>
                  <strong>{(financial_summary.debt_service_ratio * 100).toFixed(1)}%</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Monthly Cash Surplus</span>
                  <strong style={{ color: financial_summary.is_surplus_positive ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                    ₹{financial_summary.baseline_monthly_surplus.toLocaleString('en-IN')}
                  </strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Financial Situation Tier</span>
                  <span className="badge badge-cyan" style={{ textTransform: 'capitalize' }}>
                    {financial_summary.financial_situation.replace('_', ' ')}
                  </span>
                </div>
              </div>
            </div>

            {/* Optimization Allocation Breakdown */}
            <div className="card">
              <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <PieChart size={16} color="var(--accent-cyan)" /> Surplus Allocation Breakdown
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13 }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ color: 'var(--text-muted)' }}>Goal Funding Allocation (G_t)</span>
                    <strong style={{ color: 'var(--accent-emerald)' }}>
                      ₹{totalAllocated.toLocaleString('en-IN')} ({metrics.total_positive_cash_flow > 0 ? ((totalAllocated / metrics.total_positive_cash_flow) * 100).toFixed(1) : 0}%)
                    </strong>
                  </div>
                  <div className="progress-container" style={{ height: 6 }}>
                    <div
                      className="progress-fill"
                      style={{ width: `${metrics.total_positive_cash_flow > 0 ? (totalAllocated / metrics.total_positive_cash_flow) * 100 : 0}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ color: 'var(--text-muted)' }}>Residual Retained Surplus (R_t)</span>
                    <strong style={{ color: 'var(--accent-blue)' }}>
                      ₹{Math.max(0, totalResidual).toLocaleString('en-IN')} ({metrics.total_positive_cash_flow > 0 ? ((Math.max(0, totalResidual) / metrics.total_positive_cash_flow) * 100).toFixed(1) : 0}%)
                    </strong>
                  </div>
                  <div className="progress-container" style={{ height: 6 }}>
                    <div
                      style={{ height: '100%', background: 'var(--accent-blue)', borderRadius: 'var(--radius-full)', width: `${metrics.total_positive_cash_flow > 0 ? (Math.max(0, totalResidual) / metrics.total_positive_cash_flow) * 100 : 0}%` }}
                    />
                  </div>
                </div>

                <div style={{ paddingTop: 8, borderTop: '1px solid var(--border-subtle)', fontSize: 12, color: 'var(--text-secondary)' }}>
                  Average monthly goal allocation: <strong>₹{metrics.mean_monthly_goal_funding.toLocaleString('en-IN')}/mo</strong>
                </div>
              </div>
            </div>
          </div>

          {/* Warnings Section if any */}
          {warnings.length > 0 && (
            <div style={{ background: 'var(--accent-amber-dim)', border: '1px solid var(--accent-amber)', borderRadius: 'var(--radius-lg)', padding: 18, marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-amber)', fontWeight: 700, marginBottom: 8 }}>
                <ShieldAlert size={18} /> Model Alerts & Financial Observations
              </div>
              <ul style={{ paddingLeft: 20, fontSize: 13, color: '#fde68a', display: 'flex', flexDirection: 'column', gap: 6 }}>
                {warnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* "Why This Plan?" Deep Explanation Section */}
          <div className="explanation-section" style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Info size={20} color="var(--accent-emerald)" /> Why this plan?
            </h3>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.6 }}>
              {explanation.summary}
            </p>

            <div style={{ marginTop: 20 }}>
              <h4 style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent-cyan)', marginBottom: 8 }}>
                Key Model Drivers & Cash Constraints
              </h4>
              <ul className="explanation-list">
                {explanation.key_drivers.map((driver, idx) => (
                  <li key={idx} className="explanation-item">
                    <div className="explanation-item-bullet" />
                    <span>{driver}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div style={{ marginTop: 20 }}>
              <h4 style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent-emerald)', marginBottom: 8 }}>
                Role of GoalPilot Simulation Layer
              </h4>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {explanation.simulation_role}
              </p>
            </div>

            <div style={{ marginTop: 20, background: 'var(--bg-elevated)', padding: 16, borderRadius: 'var(--radius-md)' }}>
              <h4 style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-amber)', marginBottom: 8 }}>
                NISM Investor Guidance & Financial Best Practices
              </h4>
              <ul style={{ paddingLeft: 18, fontSize: 12, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                {explanation.nism_guidance_notes.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Current vs Future Notice */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 'var(--radius-md)', padding: 16, fontSize: 12, color: 'var(--text-muted)' }}>
            <strong>System Scope:</strong> {explanation.future_capabilities_notice}
          </div>
        </div>
      )}

      {/* TAB 2: MONTHLY ALLOCATION SCHEDULE TABLE */}
      {activeTab === 'schedule' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 700 }}>Monthly Longitudinal Trajectory</h3>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Dynamic inflation adjustment and optimal LP allocation ($G_t$) per period.
              </p>
            </div>
            <span className="badge badge-cyan">{monthly_schedule.length} Total Periods</span>
          </div>

          <div className="table-wrapper">
            <table className="fin-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Period</th>
                  <th>CPI Factor</th>
                  <th>Dynamic Income (₹)</th>
                  <th>Dynamic Spend (₹)</th>
                  <th>Available Surplus (₹)</th>
                  <th>Goal Funding G_t (₹)</th>
                  <th>Residual Cash R_t (₹)</th>
                  <th>Cumulative Funding (₹)</th>
                </tr>
              </thead>
              <tbody>
                {monthly_schedule.map((row) => (
                  <tr key={row.month_index}>
                    <td>#{row.month_index}</td>
                    <td>{row.period}</td>
                    <td>{row.inflation_factor.toFixed(4)}x</td>
                    <td>₹{row.income_dynamic.toLocaleString('en-IN')}</td>
                    <td>₹{row.expenditure_dynamic.toLocaleString('en-IN')}</td>
                    <td style={{ color: row.positive_cash_flow > 0 ? 'var(--accent-emerald)' : 'var(--text-muted)' }}>
                      ₹{row.positive_cash_flow.toLocaleString('en-IN')}
                    </td>
                    <td style={{ color: row.optimized_goal_funding > 0 ? 'var(--accent-cyan)' : 'var(--text-muted)', fontWeight: 600 }}>
                      ₹{row.optimized_goal_funding.toLocaleString('en-IN')}
                    </td>
                    <td style={{ color: row.residual_cash > 0 ? 'var(--accent-blue)' : 'var(--text-muted)' }}>
                      ₹{row.residual_cash.toLocaleString('en-IN')}
                    </td>
                    <td style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                      ₹{row.cumulative_goal_funding.toLocaleString('en-IN')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: BENCHMARKS & PARITY AUDIT */}
      {activeTab === 'benchmarks' && (
        <div className="card">
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>
            Research Benchmark Dataset Validation
          </h3>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>
            Click on any benchmark profile from GoalPilot AI's Step 5T / Step 5X dataset to execute real-time live optimization and verify exact parity with the research notebook.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
            {benchmarkPresetIds.map((b) => (
              <button
                key={b.id}
                className={`btn ${user_id === b.id ? 'btn-primary' : 'btn-secondary'}`}
                style={{ justifyContent: 'space-between', padding: 14 }}
                onClick={() => onSelectBenchmark(b.id)}
              >
                <span>{b.label}</span>
                <ArrowRight size={14} />
              </button>
            ))}
          </div>

          <div style={{ marginTop: 24, padding: 16, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--text-secondary)' }}>
            <strong>Mathematical Guarantees:</strong> The solver executes HiGHS simplex method with zero approximation formulas. Every benchmark case satisfies optimality residuals $\le 10^{-6}$ and target accounting conservation identities.
          </div>
        </div>
      )}
    </div>
  );
}
