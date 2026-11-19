import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api'

interface State<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
}

/** Load data from the API, re-running when `deps` change. Stale responses are ignored. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })
  const generation = useRef(0)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps)

  const reload = useCallback(() => {
    const current = ++generation.current
    setState((previous) => ({ ...previous, loading: true }))
    run().then(
      (data) => current === generation.current && setState({ data, error: null, loading: false }),
      (error: unknown) =>
        current === generation.current &&
        setState({
          data: null,
          error: error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error), 0),
          loading: false,
        }),
    )
  }, [run])

  useEffect(reload, [reload])

  const setData = useCallback((data: T) => {
    generation.current++
    setState({ data, error: null, loading: false })
  }, [])

  return { ...state, reload, setData }
}
