import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { ALL_STATUSES } from '../lib/meta'
import type { Status } from '../types'
import { statusMain } from './StatusChip'

/** A stacked bar showing how items are distributed across lifecycle statuses. */
export default function StatusBar({ counts }: { counts: Record<string, number> }) {
  const segments = ALL_STATUSES.map((status) => ({ status, count: counts[status] ?? 0 }))
  const total = segments.reduce((sum, s) => sum + s.count, 0)
  if (total === 0) return null

  return (
    <Box>
      <Box
        role="img"
        aria-label={segments.filter((s) => s.count).map((s) => `${s.count} ${s.status}`).join(', ')}
        sx={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden', gap: '2px' }}
      >
        {segments
          .filter((s) => s.count > 0)
          .map((s) => (
            <Tooltip key={s.status} title={`${s.status}: ${s.count}`}>
              <Box sx={(theme) => ({ flex: s.count, bgcolor: statusMain(theme, s.status as Status) })} />
            </Tooltip>
          ))}
      </Box>
      <Stack direction="row" useFlexGap sx={{ mt: 1.5, flexWrap: 'wrap', columnGap: 2.5, rowGap: 0.75 }}>
        {segments.map((s) => (
          <Stack key={s.status} direction="row" spacing={0.75} sx={{ alignItems: 'center', opacity: s.count ? 1 : 0.45 }}>
            <Box sx={(theme) => ({ width: 10, height: 10, borderRadius: '50%', bgcolor: statusMain(theme, s.status) })} />
            <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
              {s.status}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {s.count}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  )
}
