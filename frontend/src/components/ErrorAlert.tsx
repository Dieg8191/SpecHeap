import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import type { ApiError } from '../api'

export default function ErrorAlert({ error, onClose }: { error: ApiError; onClose?: () => void }) {
  return (
    <Alert severity="error" onClose={onClose} sx={{ mb: 2 }}>
      <AlertTitle>{error.code}</AlertTitle>
      {error.message}
      {error.hint ? <div style={{ opacity: 0.8 }}>{error.hint}</div> : null}
    </Alert>
  )
}
