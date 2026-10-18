import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AdminLayout from './components/AdminLayout'
import PublicLayout from './components/PublicLayout'
import ProtectedRoute from './auth/ProtectedRoute'
import AdminRoute from './auth/AdminRoute'

import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import Privacy from './pages/Privacy'

import Onboarding from './pages/Onboarding'
import Dashboard from './pages/Dashboard'
import ProfilePage from './pages/Profile'
import Monthly from './pages/Monthly'
import Reconciliation from './pages/Reconciliation'
import Budgets from './pages/Budgets'
import Assets from './pages/Assets'
import Liabilities from './pages/Liabilities'
import Goals from './pages/Goals'
import GoalDetailPage from './pages/GoalDetail'
import Plan from './pages/Plan'
import Optimize from './pages/Optimize'
import Admin from './pages/Admin'
import AdminLogin from './pages/AdminLogin'
import AdminRuns from './pages/AdminRuns'
import AdminRunDetail from './pages/AdminRunDetail'
import AdminUsers from './pages/AdminUsers'
import AdminHealth from './pages/AdminHealth'
import AdminAudit from './pages/AdminAudit'
import AdminData from './pages/AdminData'
import Compare from './pages/Compare'
import Scenarios from './pages/Scenarios'
import Investments from './pages/Investments'
import Loans from './pages/Loans'
import Recommendations from './pages/Recommendations'
import ForecastHistory from './pages/ForecastHistory'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Account from './pages/Account'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <Routes>
      {/* Public routes: no authentication required. */}
      <Route element={<PublicLayout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        {/* The administrator door has its own sign-in and is not part of the app shell. */}
        <Route path="/admin/login" element={<AdminLogin />} />
      </Route>

      {/* Protected routes: wrapped in ProtectedRoute. */}
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/monthly" element={<Monthly />} />
          <Route path="/monthly/reconciliation" element={<Reconciliation />} />
          <Route path="/budgets" element={<Budgets />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/assets" element={<Assets />} />
          <Route path="/liabilities" element={<Liabilities />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="/goals/:id" element={<GoalDetailPage />} />
          <Route path="/optimize" element={<Plan />} />
          {/* Algorithm choice and method comparison need the account's own data, so they live in
              the user's app; the admin area only observes runs. */}
          <Route path="/algorithms" element={<Optimize />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/scenarios" element={<Scenarios />} />
          <Route path="/investments" element={<Investments />} />
          <Route path="/loans" element={<Loans />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/account" element={<Account />} />
        </Route>
      </Route>

      {/* Technical area: separate sign-in, and only accounts with the administrator flag. */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AdminRoute />}>
          <Route element={<AdminLayout />}>
            <Route path="/admin" element={<Admin />} />
            <Route path="/admin/runs" element={<AdminRuns />} />
            <Route path="/admin/runs/:runId" element={<AdminRunDetail />} />
            <Route path="/admin/data" element={<AdminData />} />
            <Route path="/admin/model-quality" element={<ForecastHistory />} />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/admin/health" element={<AdminHealth />} />
            <Route path="/admin/audit" element={<AdminAudit />} />
          </Route>
        </Route>
      </Route>

      <Route path="/app" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}




