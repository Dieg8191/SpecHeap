import CssBaseline from '@mui/material/CssBaseline'
import useMediaQuery from '@mui/material/useMediaQuery'
import { ThemeProvider } from '@mui/material/styles'
import { StrictMode, useMemo } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { makeTheme } from './theme'

function Root() {
  const dark = useMediaQuery('(prefers-color-scheme: dark)')
  const theme = useMemo(() => makeTheme(dark ? 'dark' : 'light'), [dark])
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
