import { createTheme } from '@mui/material/styles'
import type { Theme } from '@mui/material/styles'

// System fonts only: the UI must work offline and the CSP blocks remote font hosts.
const fontFamily = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

export function makeTheme(mode: 'light' | 'dark'): Theme {
  return createTheme({
    palette: { mode },
    shape: { borderRadius: 8 },
    typography: {
      fontFamily,
      h1: { fontSize: '1.75rem', fontWeight: 700 },
      h2: { fontSize: '1.15rem', fontWeight: 600 },
    },
  })
}
