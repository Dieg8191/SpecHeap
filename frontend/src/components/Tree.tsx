import ChevronRight from '@mui/icons-material/ChevronRight'
import ExpandMore from '@mui/icons-material/ExpandMore'
import Search from '@mui/icons-material/Search'
import UnfoldLess from '@mui/icons-material/UnfoldLess'
import UnfoldMore from '@mui/icons-material/UnfoldMore'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useMemo, useState } from 'react'
import { ALL_STATUSES } from '../lib/meta'
import {
  defaultExpanded,
  expandableIds,
  filterTree,
  isFiltering,
  visibleRows,
} from '../lib/tree'
import type { TreeNode } from '../lib/tree'
import type { Status } from '../types'
import EmptyState from './EmptyState'
import { ItemLink } from './ItemRow'
import StatusChip from './StatusChip'
import TypeIcon from './TypeIcon'
import VerifSummary from './VerifSummary'

const INDENT = 22

export default function Tree({ nodes, counts }: { nodes: TreeNode[]; counts: Record<string, number> }) {
  const [query, setQuery] = useState('')
  const [statuses, setStatuses] = useState<ReadonlySet<Status>>(new Set())
  const [expanded, setExpanded] = useState<Set<string>>(() => defaultExpanded(nodes))

  const filter = useMemo(() => ({ query, statuses }), [query, statuses])
  const filtering = isFiltering(filter)
  const shown = useMemo(() => filterTree(nodes, filter), [nodes, filter])
  // While filtering, open every branch so matches are never hidden inside collapsed parents.
  const open = useMemo(() => (filtering ? new Set(expandableIds(shown)) : expanded), [filtering, shown, expanded])
  const rows = useMemo(() => visibleRows(shown, open), [shown, open])

  function toggleStatus(status: Status) {
    const next = new Set(statuses)
    if (!next.delete(status)) next.add(status)
    setStatuses(next)
  }

  function toggleNode(id: string) {
    const next = new Set(expanded)
    if (!next.delete(id)) next.add(id)
    setExpanded(next)
  }

  return (
    <Box>
      <Stack spacing={1.5} sx={{ px: 2.5, py: 1.5, borderBottom: 1, borderColor: 'divider' }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Filter by id or title"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            slotProps={{
              htmlInput: { 'aria-label': 'Filter items' },
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <Search fontSize="small" />
                  </InputAdornment>
                ),
              },
            }}
          />
          <Tooltip title="Expand all">
            <span>
              <IconButton aria-label="Expand all" disabled={filtering} onClick={() => setExpanded(new Set(expandableIds(nodes)))}>
                <UnfoldMore />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Collapse all">
            <span>
              <IconButton aria-label="Collapse all" disabled={filtering} onClick={() => setExpanded(new Set())}>
                <UnfoldLess />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
        <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 0.75 }}>
          {ALL_STATUSES.filter((status) => (counts[status] ?? 0) > 0).map((status) => (
            <Chip
              key={status}
              size="small"
              clickable
              variant={statuses.has(status) ? 'filled' : 'outlined'}
              color={statuses.has(status) ? 'primary' : 'default'}
              label={`${status} ${counts[status]}`}
              aria-pressed={statuses.has(status)}
              onClick={() => toggleStatus(status)}
              sx={{ textTransform: 'capitalize' }}
            />
          ))}
        </Stack>
      </Stack>

      {rows.length === 0 ? (
        <EmptyState>No items match this filter.</EmptyState>
      ) : (
        <Box component="ul" sx={{ m: 0, p: 0, listStyle: 'none' }}>
          {rows.map(({ node, depth }) => {
            const hasChildren = node.children.length > 0
            const isOpen = open.has(node.item.id)
            return (
              <Stack
                key={node.item.id}
                component="li"
                direction="row"
                spacing={1}
                sx={{
                  alignItems: 'center',
                  minHeight: 42,
                  pl: `${12 + depth * INDENT}px`,
                  pr: 1.5,
                  borderBottom: 1,
                  borderColor: 'divider',
                  '&:hover': { bgcolor: 'action.hover' },
                  '&:last-of-type': { borderBottom: 0 },
                }}
              >
                <IconButton
                  size="small"
                  aria-label={isOpen ? `Collapse ${node.item.id}` : `Expand ${node.item.id}`}
                  aria-expanded={hasChildren ? isOpen : undefined}
                  disabled={!hasChildren || filtering}
                  onClick={() => toggleNode(node.item.id)}
                  sx={{ visibility: hasChildren ? 'visible' : 'hidden' }}
                >
                  {isOpen ? <ExpandMore fontSize="small" /> : <ChevronRight fontSize="small" />}
                </IconButton>
                <TypeIcon type={node.item.type} size={24} />
                <Typography noWrap component="div" sx={{ flex: 1, minWidth: 0 }}>
                  <ItemLink item={node.item} />
                </Typography>
                {node.badges.map((label) => (
                  <Chip key={label} size="small" color="error" variant="outlined" label={label} />
                ))}
                <VerifSummary stats={node.stats} />
                <StatusChip status={node.item.status} />
              </Stack>
            )
          })}
        </Box>
      )}
    </Box>
  )
}
