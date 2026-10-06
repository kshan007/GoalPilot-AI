import React from 'react';
import { ArrowRight, Sparkles, CheckCircle2, TrendingUp, ShieldAlert, Cpu, Database, BarChart3 } from 'lucide-react';

export default function LandingView({ onStartPlanning, onLoadDemoPreset }) {
  const demoPresets = [
    {
      id: 'car',
      title: 'Vehicle Purchase',
      desc: 'Balanced income profile planning a ₹8,00,000 car over 36 months.',
      income: 80000,
      expenses: 40000,
      emi: 0,
      savings: 200000,
      target: 800000,
      horizon: 36,
      badge: 'Realistic Case'
    },
    {
      id: 'edu',
      title: 'Higher Education Fund',
      desc: 'Moderate income planning ₹15,00,000 for Master\'s degree over 48 months.',
      income: 95000,
      expenses: 45000,
      emi: 8000,
      savings: 300000,
      target: 1500000,
      horizon: 48,
      badge: 'High Target'
    },
    {
      id: 'deficit',
      title: 'Structural Deficit Case',
      desc: 'High expenditure and debt exceeding income to test infeasibility handling.',
      income: 50000,
      expenses: 42000,
      emi: 15000,
      savings: 20000,
      target: 200000,
      horizon: 24,
      badge: 'Deficit Test'
    }
  ];

  return (
    <div>
      {/* Hero Section */}
      <div style={{ textAlign: 'center', padding: '40px 0 60px 0' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 14px', background: 'var(--bg-elevated)', border: '1px solid var(--border-card)', borderRadius: 'var(--radius-full)', marginBottom: 20 }}>
          <Sparkles size={14} color="var(--accent-emerald)" />
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-emerald)' }}>CURRENT VERSION: Single-Goal Financial Optimization</span>
        </div>

        <h1 className="hero-title">GoalPilot</h1>
        <p style={{ fontSize: 24, fontWeight: 600, color: 'var(--accent-cyan)', marginBottom: 16 }}>
          Intelligent Financial Goal Planning
        </p>
        <p className="hero-subtitle" style={{ margin: '0 auto 36px auto' }}>
          Plan your financial goal using your income, expenses, savings and financial target — powered by GoalPilot's empirical simulation and Linear Programming optimization framework.
        </p>

        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button className="btn btn-primary btn-lg" onClick={onStartPlanning}>
            Start Planning <ArrowRight size={18} />
          </button>
          <button className="btn btn-secondary btn-lg" onClick={() => onLoadDemoPreset(demoPresets[0])}>
            Try Demo Preset
          </button>
        </div>
      </div>

      {/* How GoalPilot Works */}
      <div className="card" style={{ marginBottom: 40 }}>
        <h2 className="section-title" style={{ textAlign: 'center', marginBottom: 28 }}>
          How GoalPilot Works
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 20 }}>
          <div className="card-elevated" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--accent-emerald)', fontFamily: 'var(--font-mono)', marginBottom: 12 }}>01</div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Enter Profile</h3>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Provide monthly income, living expenses, debt EMI, and current liquid reserves.
            </p>
          </div>

          <div className="card-elevated" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)', marginBottom: 12 }}>02</div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Define Single Goal</h3>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Specify your target monetary amount and time horizon in months.
            </p>
          </div>

          <div className="card-elevated" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)', marginBottom: 12 }}>03</div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Run Optimization</h3>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Linear programming optimizes monthly allocations subject to real cash flows.
            </p>
          </div>

          <div className="card-elevated" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--accent-amber)', fontFamily: 'var(--font-mono)', marginBottom: 12 }}>04</div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Understand Plan</h3>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Examine the monthly schedule, shortfall diagnosis, and NISM investor guidance.
            </p>
          </div>
        </div>
      </div>

      {/* Preset Demo Cards */}
      <div style={{ marginBottom: 40 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <h2 className="section-title">Explore Demonstration Presets</h2>
            <p className="section-desc">Run real optimization against curated realistic financial scenarios.</p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20 }}>
          {demoPresets.map((p) => (
            <div key={p.id} className="card card-hover" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <span className={`badge ${p.id === 'deficit' ? 'badge-rose' : 'badge-emerald'}`}>
                    {p.badge}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{p.horizon} Months</span>
                </div>
                <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>{p.title}</h3>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>{p.desc}</p>

                <div style={{ background: 'var(--bg-subtle)', padding: 12, borderRadius: 'var(--radius-md)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12, marginBottom: 16 }}>
                  <div><span style={{ color: 'var(--text-muted)' }}>Income:</span> <strong>₹{p.income.toLocaleString('en-IN')}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Target:</span> <strong>₹{p.target.toLocaleString('en-IN')}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Expenses:</span> <strong>₹{p.expenses.toLocaleString('en-IN')}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Savings:</span> <strong>₹{p.savings.toLocaleString('en-IN')}</strong></div>
                </div>
              </div>

              <button className="btn btn-outline-emerald" style={{ width: '100%' }} onClick={() => onLoadDemoPreset(p)}>
                Load & Review Scenario <ArrowRight size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
