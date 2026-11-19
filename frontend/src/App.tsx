import AppBar from '@mui/material/AppBar'
import Container from '@mui/material/Container'
import Link from '@mui/material/Link'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import { Link as RouterLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import ItemPage from './pages/ItemPage'

function NotFound() {
  return (
    <>
      <Typography variant="h1" component="h1" gutterBottom>
        Page not found
      </Typography>
      <Link component={RouterLink} to="/">
        Back to overview
      </Link>
    </>
  )
}

export default function App() {
  return (
    <>
      <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Toolbar sx={{ gap: 2, flexWrap: 'wrap' }}>
          <Link component={RouterLink} to="/" underline="none" color="inherit" variant="h6" sx={{ fontWeight: 700 }}>
            SpecHeap
          </Link>
          <Typography variant="body2" color="text.secondary">
            Epic → Feature → Req → Spec → Verification
          </Typography>
        </Toolbar>
      </AppBar>
      <Container maxWidth="md" component="main" sx={{ py: 4 }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/items/:id" element={<ItemPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Container>
    </>
  )
}
