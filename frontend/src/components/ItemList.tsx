import Link from '@mui/material/Link'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'
import type { Item } from '../types'
import StatusChip from './StatusChip'

export function ItemLink({ item }: { item: Pick<Item, 'id' | 'title'> }) {
  return (
    <>
      <Link component={RouterLink} to={`/items/${item.id}`} underline="hover" sx={{ fontWeight: 600 }}>
        {item.id}
      </Link>{' '}
      {item.title}
    </>
  )
}

export function TypeLabel({ type }: { type: Item['type'] }) {
  return (
    <Typography
      variant="caption"
      color="text.secondary"
      sx={{ textTransform: 'uppercase', letterSpacing: '0.05em', minWidth: 84 }}
    >
      {type}
    </Typography>
  )
}

/** A titled list of items with their status. Renders nothing when empty. */
export default function ItemList({ title, items }: { title: string; items: Item[] }) {
  if (items.length === 0) return null
  return (
    <section>
      <Typography variant="h2" component="h2" sx={{ mt: 4, mb: 1 }}>
        {title} ({items.length})
      </Typography>
      <List disablePadding>
        {items.map((item) => (
          <ListItem key={item.id} divider sx={{ gap: 1.5 }}>
            <TypeLabel type={item.type} />
            <Typography sx={{ flex: 1, minWidth: 0 }}>
              <ItemLink item={item} />
            </Typography>
            <StatusChip status={item.status} />
          </ListItem>
        ))}
      </List>
    </section>
  )
}
