import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import Divider from '@mui/material/Divider'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'

interface Props {
  title: string
  subtitle?: string
  action?: ReactNode
  /** Render children edge to edge, for lists and tables that bring their own padding. */
  flush?: boolean
  children: ReactNode
}

export default function SectionCard({ title, subtitle, action, flush = false, children }: Props) {
  return (
    <Card component="section">
      <Stack direction="row" spacing={2} sx={{ px: 2.5, py: 1.75, alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h2" component="h2">
            {title}
          </Typography>
          {subtitle && (
            <Typography variant="body2" color="text.secondary">
              {subtitle}
            </Typography>
          )}
        </Box>
        {action}
      </Stack>
      <Divider />
      <Box sx={flush ? undefined : { p: 2.5 }}>{children}</Box>
    </Card>
  )
}
