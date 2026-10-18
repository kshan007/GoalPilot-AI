import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
  setData: (value: T | null) => void
}

/**
 * Minimal data-loading hook giving every page the four explicit states the brief requires:
 * loading, error (with a retry), empty (decided by the caller on `data`) and success.
 *
 * `deps` re-runs the loader; `reload()` re-runs it on demand (the Retry button).
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = useCallback(() => {
    const loaderRef = loader
    setLoading(true)
    setError(null)
    loaderRef()
      .then((result) => {
        if (!mounted.current) return
        setData(result)
        setLoading(false)
      })
      .catch((caught) => {
        if (!mounted.current) return
        setData(null)
        setError(errorMessage(caught))
        setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run, nonce])

  const reload = useCallback(() => setNonce((value) => value + 1), [])

  return { data, loading, error, reload, setData }
}

/**
 * Imperative action runner for buttons and forms. Keeps the four states explicit without
 * hiding the API message.
 */
export function useAction() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const run = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T | null> => {
      setPending(true)
      setError(null)
      setNotice(null)
      try {
        const result = await action()
        setPending(false)
        return result
      } catch (caught) {
        setError(errorMessage(caught))
        setPending(false)
        return null
      }
    },
    [],
  )

  return {
    pending,
    error,
    notice,
    setError,
    setNotice,
    run,
  }
}
