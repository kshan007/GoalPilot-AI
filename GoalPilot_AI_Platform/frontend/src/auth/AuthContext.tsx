import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { authApi, clearToken, errorMessage, getToken, setToken } from '../api/client'
import type { User } from '../api/types'

interface AuthContextValue {
  user: User | null
  token: string | null
  /** True while the stored token is being validated against GET /auth/me. */
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  /** Signs in through /auth/admin/login; the API refuses accounts without the flag. */
  adminLogin: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Session restore. `loading` stays true for the whole round trip so that ProtectedRoute
  // renders a loading state rather than bouncing an authenticated user to /login.
  useEffect(() => {
    let active = true
    const existing = getToken()
    if (!existing) {
      setTokenState(null)
      setUser(null)
      setLoading(false)
      return () => {
        active = false
      }
    }
    setTokenState(existing)
    authApi
      .me()
      .then((me) => {
        if (!active) return
        setUser(me)
        setError(null)
      })
      .catch((caught) => {
        if (!active) return
        setUser(null)
        setError(errorMessage(caught))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login({ email, password })
    setToken(response.access_token)
    setTokenState(response.access_token)
    setUser(response.user)
    setError(null)
  }, [])

  const adminLogin = useCallback(async (email: string, password: string) => {
    const response = await authApi.adminLogin({ email, password })
    setToken(response.access_token)
    setTokenState(response.access_token)
    setUser(response.user)
    setError(null)
  }, [])

  const register = useCallback(async (email: string, password: string, fullName: string) => {
    const response = await authApi.register({ email, password, full_name: fullName })
    setToken(response.access_token)
    setTokenState(response.access_token)
    setUser(response.user)
    setError(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // A failed sign-out must still end the local session.
    }
    clearToken()
    setTokenState(null)
    setUser(null)
  }, [])

  const refresh = useCallback(async () => {
    if (!getToken()) return
    const me = await authApi.me()
    setUser(me)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, loading, error, login, adminLogin, register, logout, refresh }),
    [user, token, loading, error, login, adminLogin, register, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside an AuthProvider')
  return context
}

export function useCurrency(): string {
  const { user } = useAuth()
  return user ? 'INR' : 'INR'
}

