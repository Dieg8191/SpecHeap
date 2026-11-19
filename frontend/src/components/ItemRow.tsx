import Box from '@mui/material/Box'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { MONO } from '../theme'
import type { Item } from '../types'
import ResultChip from './ResultChip'
import StatusChip from './StatusChip'
import TypeIcon from './TypeIcon'

/** The item id (monospace) followed by its title, as one link to the item page. */
export function ItemLink({ item }: { item: Pick<Item, 'id' | 'title'> }) {
  return (
    <Link component={RouterLink} to={`/items/${item.id}`} underline="hover" color="inherit">
      <Box component="span" sx={{ fontFamily: MONO, fontWeight: 700, fontSize: '0.85em', color: 'text.secondary', mr: 1 }}>
        {item.id}
      </Box>
      {item.title}
    </Link>
  )
}

interface RowProps {
  item: Item
  /** Show the latest verification result next to the status. */
  showResult?: boolean
  action?: ReactNode
}

export function ItemRow({ item, showResult = false, action }: RowProps) {
  return (
    <Stack
      direction="row"
      spacing={1.5}
      sx={{ px: 2.5, py: 1.25, alignItems: 'center', borderTop: 1, borderColor: 'divider', '&:first-of-type': { borderTop: 0 } }}
    >
      <TypeIcon type={item.type} />
      {/* Rows with an action are narrow, so let the title wrap instead of cutting it off. */}
      <Typography
        noWrap={!action}
        component="div"
        sx={{ flex: 1, minWidth: 0, ...(action ? { overflowWrap: 'anywhere' } : {}) }}
      >
        <ItemLink item={item} />
      </Typography>
      {showResult && item.type === 'verification' && <ResultChip result={item.result} />}
      <StatusChip status={item.status} />
      {action}
    </Stack>
  )
}

/** A card-ready list of items. */
export default function ItemRows({ items, showResult = false }: { items: Item[]; showResult?: boolean }) {
  return (
    <Box>
      {items.map((item) => (
        <ItemRow key={item.id} item={item} showResult={showResult} />
      ))}
    </Box>
  )
}
