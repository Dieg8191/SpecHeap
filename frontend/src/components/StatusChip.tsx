import Chip from '@mui/material/Chip'
import { alpha } from '@mui/material/styles'
import type { Theme } from '@mui/material/styles'
import { STATUS_COLOR } from '../lib/meta'
import type { Status } from '../types'

/** The saturated colour of a status, used for bars and dots. */
export function statusMain(theme: Theme, status: Status): string {
  const key = STATUS_COLOR[status]
  return key === 'grey' ? theme.palette.grey[500] : theme.palette[key].main
}

/** A text-safe colour for a status that keeps contrast in both themes. */
export function statusText(theme: Theme, status: Status): string {
  const key = STATUS_COLOR[status]
  if (key === 'grey') return theme.palette.text.secondary
  return theme.palette.mode === 'dark' ? theme.palette[key].light : theme.palette[key].dark
}

export default function StatusChip({ status, size = 'small' }: { status: Status; size?: 'small' | 'medium' }) {
  return (
    <Chip
      size={size}
      label={status}
      sx={(theme) => {
        const main = statusMain(theme, status)
        return {
          textTransform: 'capitalize',
          color: statusText(theme, status),
          bgcolor: alpha(main, theme.palette.mode === 'dark' ? 0.18 : 0.12),
          border: '1px solid',
          borderColor: alpha(main, 0.38),
        }
      }}
    />
  )
}
