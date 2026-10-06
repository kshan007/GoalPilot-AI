import React from 'react';
import { ArrowRight, ArrowLeft, Target, Calendar, Sparkles, AlertCircle } from 'lucide-react';

export default function GoalFormView({ goal, setGoal, profile, onNext, onBack }) {
  const income = parseFloat(profile.monthly_income) || 0;
  const expenditure = parseFloat(profile.monthly_expenditure) || 0;
  const emi = parseFloat(profile.monthly_emi) || 0;
  const surplus = income - expenditure - emi;

  const h = Math.max(1, Math.min(144, parseInt(goal.goal_horizon_months) || 12));
  const target = parseFloat(goal.target_amount) || 0;
  const flatRequiredPerMonth = target / h;
  const isSurplusSufficient = surplus * h >= target;

  const handleHorizonChange = (val) => {
    const num = Math.max(1, Math.min(144, parseInt(val) || 1));
    setGoal(prev => ({ ...prev, goal_horizon_months: num }));
  };

  const handleTargetChange = (value) => {
    if (value === '') {
      setGoal(prev => ({ ...prev, target_amount: '' }));
    } else {
      const num = parseFloat(value);
      setGoal(prev => ({ ...prev, target_amount: isNaN(num) ? '' : Math.max(0, num) }));
    }
  };

  const handleQuickTarget = (amount) => {
    setGoal(prev => ({ ...prev, target_amount: amount }));
  };

  const handleChange = (field, value) => {
    setGoal(prev => ({ ...prev, [field]: value }));
  };

  const handlePriorityChange = (priority) => {
    setGoal(prev => ({ ...prev, priority }));
  };

  const isValid = target > 0 && h >= 1 && h <= 144;

  const quickAmounts = [
    { label: '₹1 Lakh', val: 100000 },
    { label: '₹5 Lakhs', val: 500000 },
    { label: '₹10 Lakhs', val: 1000000 },
    { label: '₹25 Lakhs', val: 2500000 },
    { label: '₹50 Lakhs', val: 5000000 }
  ];

  return (
    <div style={{ maxWidth: 840, margin: '0 auto' }}>
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div>
            <h2 className="section-title">Step 2: Define Your Single Financial Goal</h2>
            <p className="section-desc">You can type any custom target amount and specify any horizon between 1 and 144 months.</p>
          </div>
          <span className="badge badge-cyan">
            Single-Goal Mode
          </span>
        </div>

        <form onSubmit={(e) => { e.preventDefault(); if (isValid) onNext(); }}>
          <div className="form-grid">
            {/* Goal Name */}
            <div className="form-group full-width">
              <label className="form-label">
                <span>Goal Label / Name *</span>
                <span className="form-label-hint">e.g. Car Down Payment, Higher Education, Home Down Payment</span>
              </label>
              <input
                type="text"
                className="input-control no-prefix"
                value={goal.goal_name || ''}
                onChange={(e) => handleChange('goal_name', e.target.value)}
                placeholder="e.g. Vehicle Purchase"
                required
              />
            </div>

            {/* Target Amount */}
            <div className="form-group">
              <label className="form-label">
                <span>Target Funding Amount *</span>
                <span className="form-label-hint">Type any custom amount in ₹</span>
              </label>
              <div className="input-wrapper">
                <span className="input-prefix">₹</span>
                <input
                  type="number"
                  className="input-control"
                  value={goal.target_amount === '' ? '' : goal.target_amount}
                  onChange={(e) => handleTargetChange(e.target.value)}
                  placeholder="Enter any amount e.g. 650000"
                  required
                  min="1"
                  step="any"
                />
              </div>

              {/* Quick Preset Buttons */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                {quickAmounts.map(qa => (
                  <button
                    key={qa.val}
                    type="button"
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: 11, padding: '3px 8px' }}
                    onClick={() => handleQuickTarget(qa.val)}
                  >
                    {qa.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Priority */}
            <div className="form-group">
              <label className="form-label">
                <span>Goal Priority Tier</span>
                <span className="form-label-hint">Essential vs. Discretionary</span>
              </label>
              <select
                className="input-control no-prefix"
                value={goal.priority || 'important'}
                onChange={(e) => handlePriorityChange(e.target.value)}
                style={{ cursor: 'pointer' }}
              >
                <option value="essential">Essential (High Priority)</option>
                <option value="important">Important (Medium Priority)</option>
                <option value="discretionary">Discretionary (Flexible)</option>
              </select>
            </div>

            {/* Goal Horizon Months Slider + Direct Input */}
            <div className="form-group full-width">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <label className="form-label" style={{ margin: 0 }}>
                  <span>Goal Horizon (Time to Achieve)</span>
                  <span className="form-label-hint">Type exact months or use slider</span>
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="number"
                    className="input-control no-prefix"
                    style={{ width: 80, padding: '4px 8px', fontSize: 14, textAlign: 'center', fontWeight: 700, color: 'var(--accent-emerald)', fontFamily: 'var(--font-mono)' }}
                    min="1"
                    max="144"
                    value={goal.goal_horizon_months || ''}
                    onChange={(e) => handleHorizonChange(e.target.value)}
                  />
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Months ({(h / 12).toFixed(1)}y)
                  </span>
                </div>
              </div>

              <div className="range-slider-wrapper">
                <input
                  type="range"
                  className="range-slider"
                  min="1"
                  max="144"
                  value={h}
                  onChange={(e) => handleHorizonChange(e.target.value)}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
                  <span>1m</span>
                  <span>12m (1y)</span>
                  <span>24m (2y)</span>
                  <span>36m (3y)</span>
                  <span>60m (5y)</span>
                  <span>120m (10y)</span>
                  <span>144m (12y max)</span>
                </div>
              </div>
            </div>

            {/* Purpose / Notes */}
            <div className="form-group full-width">
              <label className="form-label">
                <span>Purpose / Context (Optional)</span>
                <span className="form-label-hint">Additional context for plan documentation</span>
              </label>
              <input
                type="text"
                className="input-control no-prefix"
                value={goal.purpose || ''}
                onChange={(e) => handleChange('purpose', e.target.value)}
                placeholder="e.g. Planning purchase for family mobility with minimal debt"
              />
            </div>
          </div>

          {/* Goal Feasibility Estimate Banner */}
          <div style={{ marginTop: 24, padding: 18, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, fontSize: 13 }}>
            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>Required Flat Monthly Savings</div>
              <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--accent-cyan)' }}>
                ₹{Math.round(flatRequiredPerMonth).toLocaleString('en-IN')} / mo
              </div>
            </div>

            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>Current Baseline Monthly Surplus</div>
              <div style={{ fontWeight: 700, fontSize: 16, color: surplus >= flatRequiredPerMonth ? 'var(--accent-emerald)' : 'var(--accent-amber)' }}>
                ₹{Math.round(surplus).toLocaleString('en-IN')} / mo
              </div>
            </div>

            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>Preliminary Horizon Sufficiency</div>
              <div style={{ fontWeight: 700, fontSize: 15, color: isSurplusSufficient ? 'var(--accent-emerald)' : 'var(--accent-amber)' }}>
                {isSurplusSufficient ? 'Surplus Appears Sufficient' : 'Potential Shortfall Expected'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 32 }}>
            <button type="button" className="btn btn-secondary" onClick={onBack}>
              <ArrowLeft size={16} /> Back to Profile
            </button>
            <button type="submit" className="btn btn-primary" disabled={!isValid}>
              Review Information <ArrowRight size={16} />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
