import Cancel from '@mui/icons-material/Cancel'
import CheckCircle from '@mui/icons-material/CheckCircle'
import Remove from '@mui/icons-material/Remove'
import Chip from '@mui/material/Chip'
import type { VerificationResult } from '../types'

/** The outcome of the latest run of a verification; `null` means it never ran. */
export default function ResultChip({ result, size = 'small' }: { result: VerificationResult | null; size?: 'small' | 'medium' }) {
  if (result === 'pass') return <Chip size={size} color="success" variant="outlined" icon={<CheckCircle />} label="pass" />
  if (result === 'fail') return <Chip size={size} color="error" variant="outlined" icon={<Cancel />} label="fail" />
  if (result === 'skipped') return <Chip size={size} variant="outlined" icon={<Remove />} label="skipped" />
  return <Chip size={size} variant="outlined" label="not run" sx={{ borderStyle: 'dashed', color: 'text.secondary' }} />
}
