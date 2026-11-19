import CssBaseline from '@mui/material/CssBaseline'
import useMediaQuery from '@mui/material/useMediaQuery'
import { ThemeProvider } from '@mui/material/styles'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { makeTheme } from './theme'

type Mode = 'light' | 'dark'
const STORAGE_KEY = 'specheap-color-mode'

const ColorModeContext = createContext<{ mode: Mode; toggle: () => void }>({ mode: 'light', toggle: () => {} })

function readStored(): Mode | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null // Storage can be unavailable (private windows, blocked site data).
  }
}

/** Follows the system colour scheme until the user picks one with the toggle. */
export function ColorModeProvider({ children }: { children: ReactNode }) {
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)')
  const [override, setOverride] = useState<Mode | null>(readStored)
  const mode: Mode = override ?? (systemDark ? 'dark' : 'light')

  const toggle = useCallback(() => {
    const next: Mode = mode === 'dark' ? 'light' : 'dark'
    setOverride(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Not persisting is fine; the choice still applies for this session.
    }
  }, [mode])

  const theme = useMemo(() => makeTheme(mode), [mode])
  const value = useMemo(() => ({ mode, toggle }), [mode, toggle])

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  )
}

export function useColorMode() {
  return useContext(ColorModeContext)
}
