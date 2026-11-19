import DarkMode from '@mui/icons-material/DarkMode'
import Hub from '@mui/icons-material/Hub'
import LightMode from '@mui/icons-material/LightMode'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Container from '@mui/material/Container'
import IconButton from '@mui/material/IconButton'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Toolbar from '@mui/material/Toolbar'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { alpha } from '@mui/material/styles'
import { Link as RouterLink, Route, Routes } from 'react-router-dom'
import { useColorMode } from './colorMode'
import Dashboard from './pages/Dashboard'
import ItemPage from './pages/ItemPage'

function NotFound() {
  return (
    <Stack spacing={2} sx={{ alignItems: 'flex-start' }}>
      <Typography variant="h1" component="h1">
        Page not found
      </Typography>
      <Link component={RouterLink} to="/">
        Back to overview
      </Link>
    </Stack>
  )
}

function Header() {
  const { mode, toggle } = useColorMode()
  return (
    <AppBar
      position="sticky"
      color="inherit"
      elevation={0}
      sx={(theme) => ({
        borderBottom: 1,
        borderColor: 'divider',
        backdropFilter: 'blur(8px)',
        bgcolor: alpha(theme.palette.background.paper, 0.85),
      })}
    >
      <Container maxWidth="lg" disableGutters sx={{ px: { xs: 2, sm: 3 } }}>
        <Toolbar disableGutters sx={{ gap: 2 }}>
          <Link component={RouterLink} to="/" underline="none" color="inherit" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{ width: 30, height: 30, display: 'grid', placeItems: 'center', borderRadius: 1.5, bgcolor: 'primary.main', color: 'primary.contrastText' }}>
              <Hub sx={{ fontSize: 19 }} />
            </Box>
            <Typography sx={{ fontWeight: 700, fontSize: '1.05rem', letterSpacing: '-0.01em' }}>SpecHeap</Typography>
          </Link>
          <Typography variant="body2" color="text.secondary" sx={{ display: { xs: 'none', md: 'block' } }}>
            Epic → Feature → Requirement → Spec → Verification
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Tooltip title={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
            <IconButton aria-label="Toggle color mode" onClick={toggle}>
              {mode === 'dark' ? <LightMode /> : <DarkMode />}
            </IconButton>
          </Tooltip>
        </Toolbar>
      </Container>
    </AppBar>
  )
}

export default function App() {
  return (
    <>
      <Header />
      <Container maxWidth="lg" component="main" sx={{ py: 4, px: { xs: 2, sm: 3 } }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/items/:id" element={<ItemPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Container>
    </>
  )
}
