import React, { useEffect, useState } from 'react';
import { Cpu, Database, CheckCircle2, Loader2, Sparkles } from 'lucide-react';

export default function OptimizingLoader() {
  const [stage, setStage] = useState(1);

  useEffect(() => {
    const t1 = setTimeout(() => setStage(2), 350);
    const t2 = setTimeout(() => setStage(3), 750);
    const t3 = setTimeout(() => setStage(4), 1150);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, []);

  const steps = [
    { num: 1, label: 'Calibrating Empirical CPI Inflation Schedule' },
    { num: 2, label: 'Generating Dynamic Monthly Cash Flow Trajectory' },
    { num: 3, label: 'Executing HiGHS Linear Programming Solver (Step 5T)' },
    { num: 4, label: 'Verifying Invariants & Analytical Optimality Bounds' }
  ];

  return (
    <div style={{ maxWidth: 580, margin: '80px auto', textAlign: 'center' }}>
      <div style={{ position: 'relative', width: 80, height: 80, margin: '0 auto 28px auto' }}>
        <div style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          border: '3px solid var(--border-card)',
          borderTopColor: 'var(--accent-emerald)',
          animation: 'spin 1s linear infinite'
        }} />
        <div style={{
          position: 'absolute',
          inset: 10,
          borderRadius: '50%',
          background: 'var(--bg-elevated)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--accent-emerald)'
        }}>
          <Cpu size={28} />
        </div>
      </div>

      <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>GoalPilot Optimizer Running</h2>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 36 }}>
        Evaluating your financial profile against the empirical simulation dataset...
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, textAlign: 'left', background: 'var(--bg-card)', padding: 24, borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-card)' }}>
        {steps.map((s) => {
          const isDone = stage > s.num;
          const isCurrent = stage === s.num;

          return (
            <div key={s.num} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13 }}>
              {isDone ? (
                <CheckCircle2 size={18} color="var(--accent-emerald)" style={{ flexShrink: 0 }} />
              ) : isCurrent ? (
                <Loader2 size={18} color="var(--accent-cyan)" className="animate-spin" style={{ flexShrink: 0 }} />
              ) : (
                <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid var(--border-card)', flexShrink: 0 }} />
              )}
              <span style={{ color: isDone ? 'var(--text-primary)' : (isCurrent ? 'var(--accent-cyan)' : 'var(--text-muted)'), fontWeight: isCurrent ? 600 : 400 }}>
                {s.label}
              </span>
            </div>
          );
        })}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .animate-spin {
          animation: spin 1s linear infinite;
        }
      `}</style>
    </div>
  );
}
