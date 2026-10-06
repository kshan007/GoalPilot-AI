import React, { useState } from 'react';
import LandingView from './components/LandingView.jsx';
import ProfileFormView from './components/ProfileFormView.jsx';
import GoalFormView from './components/GoalFormView.jsx';
import ReviewView from './components/ReviewView.jsx';
import OptimizingLoader from './components/OptimizingLoader.jsx';
import ResultsDashboard from './components/ResultsDashboard.jsx';
import { Compass, Sparkles, AlertCircle } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export default function App() {
  const [currentStep, setCurrentStep] = useState('landing'); // landing | profile | goal | review | optimizing | results
  const [errorMessage, setErrorMessage] = useState(null);

  // Financial Profile State
  const [profile, setProfile] = useState({
    monthly_income: 80000,
    monthly_expenditure: 40000,
    monthly_emi: 0,
    initial_savings: 200000,
    initial_investment: 50000,
    risk_profile: 'moderate'
  });

  // Single Goal State
  const [goal, setGoal] = useState({
    goal_name: 'Vehicle Purchase',
    target_amount: 800000,
    goal_horizon_months: 36,
    priority: 'important',
    purpose: 'Personal mobility with minimal high-cost borrowing'
  });

  // Optimization Result State
  const [optimizationResult, setOptimizationResult] = useState(null);

  // Handlers
  const handleLoadDemoPreset = (preset) => {
    setProfile({
      monthly_income: preset.income,
      monthly_expenditure: preset.expenses,
      monthly_emi: preset.emi,
      initial_savings: preset.savings,
      initial_investment: 50000,
      risk_profile: 'moderate'
    });
    setGoal({
      goal_name: preset.title,
      target_amount: preset.target,
      goal_horizon_months: preset.horizon,
      priority: 'important',
      purpose: preset.desc
    });
    setCurrentStep('review');
    setErrorMessage(null);
  };

  const handleRunOptimization = async () => {
    setCurrentStep('optimizing');
    setErrorMessage(null);

    try {
      const payload = {
        user_id: 'USER_CUSTOM',
        financial_profile: {
          monthly_income: parseFloat(profile.monthly_income) || 0,
          monthly_expenditure: parseFloat(profile.monthly_expenditure) || 0,
          monthly_emi: parseFloat(profile.monthly_emi) || 0,
          initial_savings: parseFloat(profile.initial_savings) || 0,
          initial_investment: parseFloat(profile.initial_investment) || 0,
          risk_profile: profile.risk_profile || 'moderate'
        },
        goal: {
          goal_name: goal.goal_name || 'Primary Goal',
          target_amount: parseFloat(goal.target_amount) || 0,
          goal_horizon_months: parseInt(goal.goal_horizon_months) || 12,
          priority: goal.priority || 'important',
          purpose: goal.purpose || ''
        }
      };

      const res = await fetch(`${API_BASE}/api/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Optimization request failed' }));
        throw new Error(errData.detail || `Server returned status ${res.status}`);
      }

      const data = await res.json();
      setTimeout(() => {
        setOptimizationResult(data);
        setCurrentStep('results');
      }, 1000);
    } catch (err) {
      console.error('Optimization error:', err);
      setErrorMessage(err.message || 'Failed to complete optimization. Please check your network and inputs.');
      setCurrentStep('review');
    }
  };

  const handleSelectBenchmark = async (benchmarkUserId) => {
    setCurrentStep('optimizing');
    setErrorMessage(null);

    try {
      const res = await fetch(`${API_BASE}/api/benchmarks/run/${benchmarkUserId}`, {
        method: 'POST'
      });

      if (!res.ok) {
        throw new Error(`Failed to load benchmark user ${benchmarkUserId}`);
      }

      const data = await res.json();
      setTimeout(() => {
        setOptimizationResult(data);
        setCurrentStep('results');
      }, 800);
    } catch (err) {
      console.error('Benchmark execution error:', err);
      setErrorMessage(`Benchmark execution error: ${err.message}`);
      setCurrentStep('results');
    }
  };

  const handleResetToLanding = () => {
    setCurrentStep('landing');
    setErrorMessage(null);
  };

  return (
    <div className="app-container">
      <div className="ambient-glow" />

      {/* Header */}
      <header className="app-header">
        <div className="brand" onClick={handleResetToLanding}>
          <div className="brand-icon">
            <Compass size={24} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="brand-title">GoalPilot</span>
              <span className="brand-badge">Single-Goal Engine</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>
              AI Optimization & Simulation Platform
            </div>
          </div>
        </div>

        <div className="header-actions">
          {currentStep !== 'landing' && (
            <button className="btn btn-secondary btn-sm" onClick={handleResetToLanding}>
              Home
            </button>
          )}
          <button
            className="btn btn-outline-emerald btn-sm"
            onClick={() => handleLoadDemoPreset({
              title: 'Car Purchase Demo',
              desc: 'Standard ₹8,00,000 vehicle purchase over 36 months.',
              income: 80000,
              expenses: 40000,
              emi: 0,
              savings: 200000,
              target: 800000,
              horizon: 36
            })}
          >
            <Sparkles size={14} /> Quick Demo
          </button>
        </div>
      </header>

      {/* Error Notification Banner */}
      {errorMessage && (
        <div style={{
          background: 'var(--accent-rose-dim)',
          border: '1px solid var(--accent-rose)',
          borderRadius: 'var(--radius-md)',
          padding: 14,
          marginBottom: 24,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          color: '#fecdd3',
          fontSize: 13
        }}>
          <AlertCircle size={18} style={{ flexShrink: 0 }} />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Stepper (for Wizard stages) */}
      {['profile', 'goal', 'review', 'results'].includes(currentStep) && (
        <div className="wizard-stepper">
          <div
            className={`step-item ${currentStep === 'profile' ? 'active' : (['goal', 'review', 'results'].includes(currentStep) ? 'completed' : '')}`}
            onClick={() => setCurrentStep('profile')}
          >
            <div className="step-circle">1</div>
            <span>Profile</span>
          </div>
          <div className={`step-line ${['goal', 'review', 'results'].includes(currentStep) ? 'completed' : ''}`} />

          <div
            className={`step-item ${currentStep === 'goal' ? 'active' : (['review', 'results'].includes(currentStep) ? 'completed' : '')}`}
            onClick={() => setCurrentStep('goal')}
          >
            <div className="step-circle">2</div>
            <span>Single Goal</span>
          </div>
          <div className={`step-line ${['review', 'results'].includes(currentStep) ? 'completed' : ''}`} />

          <div
            className={`step-item ${currentStep === 'review' ? 'active' : (currentStep === 'results' ? 'completed' : '')}`}
            onClick={() => setCurrentStep('review')}
          >
            <div className="step-circle">3</div>
            <span>Review</span>
          </div>
          <div className={`step-line ${currentStep === 'results' ? 'completed' : ''}`} />

          <div className={`step-item ${currentStep === 'results' ? 'active completed' : ''}`}>
            <div className="step-circle">4</div>
            <span>Optimized Plan</span>
          </div>
        </div>
      )}

      {/* Main Content Stage View Router */}
      <main>
        {currentStep === 'landing' && (
          <LandingView
            onStartPlanning={() => setCurrentStep('profile')}
            onLoadDemoPreset={handleLoadDemoPreset}
          />
        )}

        {currentStep === 'profile' && (
          <ProfileFormView
            profile={profile}
            setProfile={setProfile}
            onNext={() => setCurrentStep('goal')}
            onBack={() => setCurrentStep('landing')}
          />
        )}

        {currentStep === 'goal' && (
          <GoalFormView
            goal={goal}
            setGoal={setGoal}
            profile={profile}
            onNext={() => setCurrentStep('review')}
            onBack={() => setCurrentStep('profile')}
          />
        )}

        {currentStep === 'review' && (
          <ReviewView
            profile={profile}
            goal={goal}
            onEditProfile={() => setCurrentStep('profile')}
            onEditGoal={() => setCurrentStep('goal')}
            onRunOptimization={handleRunOptimization}
            isRunning={false}
          />
        )}

        {currentStep === 'optimizing' && (
          <OptimizingLoader />
        )}

        {currentStep === 'results' && (
          <ResultsDashboard
            result={optimizationResult}
            onReset={handleResetToLanding}
            onModifyInputs={() => setCurrentStep('profile')}
            onSelectBenchmark={handleSelectBenchmark}
          />
        )}
      </main>

      {/* Regulatory & Prototype Disclaimer Footer */}
      <footer className="app-footer">
        <p>
          <strong>Regulatory & Research Disclaimer:</strong> GoalPilot is an educational and research prototype for financial planning and decision support. It does not constitute personalized regulated financial advice and does not guarantee investment returns.
        </p>
        <p style={{ marginTop: 6, fontSize: 11, color: 'var(--text-dim)' }}>
          Powered by GoalPilot AI Longitudinal Simulation & Scipy HiGHS Linear Programming Solver • Version 1.0.0
        </p>
      </footer>
    </div>
  );
}
