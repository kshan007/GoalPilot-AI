import React from 'react';
import { ArrowLeft, Play, Edit3, CheckCircle, ShieldCheck, HelpCircle } from 'lucide-react';

export default function ReviewView({ profile, goal, onEditProfile, onEditGoal, onRunOptimization, isRunning }) {
  const surplus = profile.monthly_income - profile.monthly_expenditure - profile.monthly_emi;
  const h = parseInt(goal.goal_horizon_months) || 12;
  const target = parseFloat(goal.target_amount) || 0;

  return (
    <div style={{ maxWidth: 880, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <h2 className="section-title">Step 3: Review Your Planning Data</h2>
        <p className="section-desc">Verify your financial profile and single financial goal before executing the optimization engine.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>
        {/* Financial Profile Card */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
              <ShieldCheck size={18} color="var(--accent-emerald)" /> Financial Profile
            </h3>
            <button className="btn btn-secondary btn-sm" onClick={onEditProfile}>
              <Edit3 size={13} /> Edit
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Gross Monthly Income</span>
              <strong>₹{profile.monthly_income.toLocaleString('en-IN')}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Monthly Living Expenses</span>
              <strong>₹{profile.monthly_expenditure.toLocaleString('en-IN')}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Monthly Debt EMI</span>
              <strong>₹{profile.monthly_emi.toLocaleString('en-IN')}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Baseline Monthly Surplus</span>
              <strong style={{ color: surplus >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                ₹{surplus.toLocaleString('en-IN')}
              </strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Liquid Savings Balance</span>
              <strong>₹{profile.initial_savings.toLocaleString('en-IN')}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Risk Profile Tier</span>
              <span className="badge badge-cyan" style={{ textTransform: 'capitalize' }}>
                {profile.risk_profile}
              </span>
            </div>
          </div>
        </div>

        {/* Goal Card */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
              <CheckCircle size={18} color="var(--accent-cyan)" /> Single Financial Goal
            </h3>
            <button className="btn btn-secondary btn-sm" onClick={onEditGoal}>
              <Edit3 size={13} /> Edit
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Goal Name</span>
              <strong>{goal.goal_name || 'Primary Goal'}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Target Amount</span>
              <strong style={{ color: 'var(--accent-cyan)', fontSize: 15 }}>
                ₹{target.toLocaleString('en-IN')}
              </strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Goal Horizon</span>
              <strong>{h} Months ({(h / 12).toFixed(1)} Years)</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Priority Classification</span>
              <span className="badge badge-emerald" style={{ textTransform: 'capitalize' }}>
                {goal.priority || 'important'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Required Flat Monthly</span>
              <strong>₹{Math.round(target / h).toLocaleString('en-IN')} / mo</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Purpose</span>
              <span style={{ maxWidth: 180, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {goal.purpose || 'Not specified'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Model Execution Notice */}
      <div className="card-highlight card" style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <HelpCircle size={20} color="var(--accent-emerald)" style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>What happens when you run GoalPilot?</strong>
            <p style={{ marginTop: 4 }}>
              1. The backend converts your financial profile into the <strong>calibrated CPI inflation trajectory</strong>.<br />
              2. It dynamically simulates your monthly surplus and positive cash flow boundary across all {h} months.<br />
              3. The <strong>HiGHS Linear Programming Solver</strong> solves for optimal monthly contributions minimizing goal shortfall.<br />
              4. You receive the exact, mathematically guaranteed allocation schedule.
            </p>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button type="button" className="btn btn-secondary" onClick={onEditGoal}>
          <ArrowLeft size={16} /> Back to Goal
        </button>

        <button
          type="button"
          className="btn btn-primary btn-lg"
          onClick={onRunOptimization}
          disabled={isRunning}
        >
          {isRunning ? (
            <span>Optimizing Plan...</span>
          ) : (
            <>
              <Play size={18} /> Run GoalPilot Optimization
            </>
          )}
        </button>
      </div>
    </div>
  );
}
