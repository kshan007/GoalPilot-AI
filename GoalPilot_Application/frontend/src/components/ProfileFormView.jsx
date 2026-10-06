import React from 'react';
import { ArrowRight, ArrowLeft, Wallet, Shield, AlertCircle, Check, DollarSign } from 'lucide-react';

export default function ProfileFormView({ profile, setProfile, onNext, onBack }) {
  const income = parseFloat(profile.monthly_income) || 0;
  const expenditure = parseFloat(profile.monthly_expenditure) || 0;
  const emi = parseFloat(profile.monthly_emi) || 0;
  const savings = parseFloat(profile.initial_savings) || 0;

  const surplus = income - expenditure - emi;
  const emiRatio = income > 0 ? (emi / income) * 100 : 0;
  const emergencyMonths = expenditure > 0 ? (savings / expenditure) : 0;

  const handleChange = (field, value) => {
    // Keep empty string if user cleared the input so they can type freely
    if (value === '') {
      setProfile(prev => ({ ...prev, [field]: '' }));
    } else {
      const num = parseFloat(value);
      setProfile(prev => ({ ...prev, [field]: isNaN(num) ? '' : Math.max(0, num) }));
    }
  };

  const handleRiskChange = (risk) => {
    setProfile(prev => ({ ...prev, risk_profile: risk }));
  };

  const isValid = income > 0;

  return (
    <div style={{ maxWidth: 840, margin: '0 auto' }}>
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div>
            <h2 className="section-title">Step 1: Your Financial Profile</h2>
            <p className="section-desc">Enter your exact cash flows, debt commitments, and liquid balances. You can type any custom value.</p>
          </div>
          <span className={`badge ${surplus > 0 ? 'badge-emerald' : 'badge-rose'}`}>
            Monthly Surplus: ₹{Math.round(surplus).toLocaleString('en-IN')}
          </span>
        </div>

        <form onSubmit={(e) => { e.preventDefault(); if (isValid) onNext(); }}>
          <div className="form-grid">
            {/* Monthly Income */}
            <div className="form-group">
              <label className="form-label">
                <span>Monthly Gross Income *</span>
                <span className="form-label-hint">₹ / month (Any custom amount)</span>
              </label>
              <div className="input-wrapper">
                <span className="input-prefix">₹</span>
                <input
                  type="number"
                  className="input-control"
                  value={profile.monthly_income === '' ? '' : profile.monthly_income}
                  onChange={(e) => handleChange('monthly_income', e.target.value)}
                  placeholder="Enter any amount e.g. 85000"
                  required
                  min="1"
                  step="any"
                />
              </div>
            </div>

            {/* Monthly Expenditure */}
            <div className="form-group">
              <label className="form-label">
                <span>Monthly Living Expenses *</span>
                <span className="form-label-hint">Essential + Discretionary</span>
              </label>
              <div className="input-wrapper">
                <span className="input-prefix">₹</span>
                <input
                  type="number"
                  className="input-control"
                  value={profile.monthly_expenditure === '' ? '' : profile.monthly_expenditure}
                  onChange={(e) => handleChange('monthly_expenditure', e.target.value)}
                  placeholder="Enter any amount e.g. 42500"
                  min="0"
                  step="any"
                />
              </div>
            </div>

            {/* Monthly EMI */}
            <div className="form-group">
              <label className="form-label">
                <span>Monthly Debt EMI</span>
                <span className="form-label-hint">Loans, Mortgages, Credit EMIs</span>
              </label>
              <div className="input-wrapper">
                <span className="input-prefix">₹</span>
                <input
                  type="number"
                  className="input-control"
                  value={profile.monthly_emi === '' ? '' : profile.monthly_emi}
                  onChange={(e) => handleChange('monthly_emi', e.target.value)}
                  placeholder="Enter EMI e.g. 0 or 12000"
                  min="0"
                  step="any"
                />
              </div>
            </div>

            {/* Current Savings */}
            <div className="form-group">
              <label className="form-label">
                <span>Current Liquid Savings</span>
                <span className="form-label-hint">Bank FD, Savings Account</span>
              </label>
              <div className="input-wrapper">
                <span className="input-prefix">₹</span>
                <input
                  type="number"
                  className="input-control"
                  value={profile.initial_savings === '' ? '' : profile.initial_savings}
                  onChange={(e) => handleChange('initial_savings', e.target.value)}
                  placeholder="Enter savings e.g. 200000"
                  min="0"
                  step="any"
                />
              </div>
            </div>

            {/* Current Investments */}
            <div className="form-group">
              <label className="form-label">
                <span>Existing Investments</span>
                <span className="form-label-hint">Mutual Funds, Stocks, Gold</span>
              </label>
              <div className="input-wrapper">
                <span className="input-prefix">₹</span>
                <input
                  type="number"
                  className="input-control"
                  value={profile.initial_investment === '' ? '' : profile.initial_investment}
                  onChange={(e) => handleChange('initial_investment', e.target.value)}
                  placeholder="Enter investments e.g. 50000"
                  min="0"
                  step="any"
                />
              </div>
            </div>

            {/* Risk Profile */}
            <div className="form-group full-width">
              <label className="form-label">
                <span>Risk Preference Tier</span>
                <span className="form-label-hint">Used for educational asset matching</span>
              </label>
              <div className="radio-card-grid">
                <div
                  className={`radio-card ${profile.risk_profile === 'conservative' ? 'active' : ''}`}
                  onClick={() => handleRiskChange('conservative')}
                >
                  <div className="radio-card-title">Conservative</div>
                  <div className="radio-card-desc">Prioritizes capital protection with fixed deposits & debt.</div>
                </div>

                <div
                  className={`radio-card ${profile.risk_profile === 'moderate' ? 'active' : ''}`}
                  onClick={() => handleRiskChange('moderate')}
                >
                  <div className="radio-card-title">Moderate</div>
                  <div className="radio-card-desc">Balanced growth through hybrid debt-equity allocations.</div>
                </div>

                <div
                  className={`radio-card ${profile.risk_profile === 'aggressive' ? 'active' : ''}`}
                  onClick={() => handleRiskChange('aggressive')}
                >
                  <div className="radio-card-title">Aggressive</div>
                  <div className="radio-card-desc">Higher equity market exposure for long-term compounding.</div>
                </div>
              </div>
            </div>
          </div>

          {/* Real-time Health Insights Box */}
          <div style={{ marginTop: 24, padding: 16, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14, fontSize: 13 }}>
            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>Monthly Cash Surplus</div>
              <div style={{ fontWeight: 700, fontSize: 16, color: surplus >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                ₹{Math.round(surplus).toLocaleString('en-IN')}
              </div>
            </div>

            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>Debt-to-Income (EMI Ratio)</div>
              <div style={{ fontWeight: 700, fontSize: 16, color: emiRatio > 40 ? 'var(--accent-amber)' : 'var(--text-primary)' }}>
                {emiRatio.toFixed(1)}% {emiRatio > 40 && <span style={{ fontSize: 11, color: 'var(--accent-amber)' }}>(High)</span>}
              </div>
            </div>

            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 2 }}>Emergency Fund Coverage</div>
              <div style={{ fontWeight: 700, fontSize: 16, color: emergencyMonths >= 6 ? 'var(--accent-emerald)' : (emergencyMonths >= 3 ? 'var(--accent-cyan)' : 'var(--accent-amber)') }}>
                {emergencyMonths.toFixed(1)} Months {emergencyMonths < 3 && <span style={{ fontSize: 11, color: 'var(--accent-amber)' }}>(Needs buffer)</span>}
              </div>
            </div>
          </div>

          {surplus <= 0 && (
            <div style={{ marginTop: 16, padding: 12, background: 'var(--accent-rose-dim)', border: '1px solid var(--accent-rose)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: '#fca5a5' }}>
              <AlertCircle size={18} style={{ flexShrink: 0 }} />
              <span>Warning: Your monthly living expenses and debt EMI exceed your income. Optimization may report a structural deficit.</span>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 32 }}>
            <button type="button" className="btn btn-secondary" onClick={onBack}>
              <ArrowLeft size={16} /> Back to Landing
            </button>
            <button type="submit" className="btn btn-primary" disabled={!isValid}>
              Proceed to Goal Definition <ArrowRight size={16} />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
