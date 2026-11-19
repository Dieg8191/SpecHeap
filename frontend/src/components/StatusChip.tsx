import Chip from '@mui/material/Chip'
import type { ChipProps } from '@mui/material/Chip'
import type { Status } from '../types'

const COLORS: Record<Status, ChipProps['color']> = {
  draft: 'default',
  proposed: 'warning',
  approved: 'info',
  implemented: 'secondary',
  verified: 'success',
  stale: 'error',
}

export default function StatusChip({ status }: { status: Status }) {
  return <Chip size="small" variant="outlined" color={COLORS[status]} label={status} />
}
