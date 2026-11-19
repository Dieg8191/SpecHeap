import Description from '@mui/icons-material/Description'
import Extension from '@mui/icons-material/Extension'
import FactCheck from '@mui/icons-material/FactCheck'
import Layers from '@mui/icons-material/Layers'
import Rule from '@mui/icons-material/Rule'
import Box from '@mui/material/Box'
import Tooltip from '@mui/material/Tooltip'
import { alpha } from '@mui/material/styles'
import type { SvgIconComponent } from '@mui/icons-material'
import { TYPE_LABEL } from '../lib/meta'
import type { ItemType } from '../types'

const ICONS: Record<ItemType, SvgIconComponent> = {
  epic: Layers,
  feature: Extension,
  req: Rule,
  spec: Description,
  verification: FactCheck,
}

/** A tinted tile with the icon of the item type, so levels can be told apart at a glance. */
export default function TypeIcon({ type, size = 28 }: { type: ItemType; size?: number }) {
  const Icon = ICONS[type]
  return (
    <Tooltip title={TYPE_LABEL[type]}>
      <Box
        aria-label={TYPE_LABEL[type]}
        role="img"
        sx={(theme) => ({
          width: size,
          height: size,
          flexShrink: 0,
          display: 'grid',
          placeItems: 'center',
          borderRadius: 1.5,
          color: 'primary.main',
          bgcolor: alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.16 : 0.1),
        })}
      >
        <Icon sx={{ fontSize: size * 0.62 }} />
      </Box>
    </Tooltip>
  )
}
