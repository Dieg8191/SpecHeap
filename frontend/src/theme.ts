import { createTheme } from '@mui/material/styles'
import type { Theme } from '@mui/material/styles'

// System fonts only: the UI must work offline and the CSP blocks remote font hosts.
const fontFamily = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
export const MONO = 'ui-monospace, SFMono-Regular, "Cascadia Code", Menlo, Consolas, monospace'

export function makeTheme(mode: 'light' | 'dark'): Theme {
  const dark = mode === 'dark'
  return createTheme({
    palette: {
      mode,
      primary: { main: dark ? '#8ea2ff' : '#4155d6' },
      background: dark
        ? { default: '#0d0f14', paper: '#151821' }
        : { default: '#f4f5f9', paper: '#ffffff' },
      divider: dark ? 'rgba(255,255,255,0.09)' : 'rgba(15,23,42,0.10)',
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily,
      fontSize: 14,
      h1: { fontSize: '1.6rem', fontWeight: 700, letterSpacing: '-0.015em', lineHeight: 1.25 },
      h2: { fontSize: '0.95rem', fontWeight: 650 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    components: {
      MuiCard: { defaultProps: { variant: 'outlined' }, styleOverrides: { root: { backgroundImage: 'none' } } },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
      MuiTooltip: { defaultProps: { arrow: true } },
    },
  })
}
