import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'

export default function EmptyState({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <Stack spacing={1} sx={{ alignItems: 'center', py: 4, px: 2, color: 'text.secondary', textAlign: 'center' }}>
      {icon}
      <Typography variant="body2">{children}</Typography>
    </Stack>
  )
}
