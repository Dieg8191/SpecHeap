import Cancel from '@mui/icons-material/Cancel'
import CheckCircle from '@mui/icons-material/CheckCircle'
import Schedule from '@mui/icons-material/Schedule'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import type { VerificationStats } from '../lib/tree'

/** "3/3" with an icon: how many of an item's verifications pass. */
export default function VerifSummary({ stats }: { stats: VerificationStats | null }) {
  if (!stats || stats.total === 0) return null
  const allPass = stats.pass === stats.total
  const color = stats.fail > 0 ? 'error.main' : allPass ? 'success.main' : 'warning.main'
  const Icon = stats.fail > 0 ? Cancel : allPass ? CheckCircle : Schedule
  const label = `${stats.pass} of ${stats.total} verifications pass${stats.fail > 0 ? `, ${stats.fail} failing` : ''}`
  return (
    <Tooltip title={label}>
      <Stack direction="row" spacing={0.5} aria-label={label} sx={{ alignItems: 'center', color }}>
        <Icon sx={{ fontSize: 16 }} />
        <Typography variant="caption" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
          {stats.pass}/{stats.total}
        </Typography>
      </Stack>
    </Tooltip>
  )
}
