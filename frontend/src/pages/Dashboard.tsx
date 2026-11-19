import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { api } from '../api'
import type { ApiError } from '../api'
import ActionButtons from '../components/ActionButtons'
import ErrorAlert from '../components/ErrorAlert'
import { ItemLink, TypeLabel } from '../components/ItemList'
import StatusChip from '../components/StatusChip'
import Tree from '../components/Tree'
import { useApi } from '../hooks/useApi'
import { buildTree, gapLabels } from '../lib/tree'
import type { ActionView, Dashboard as DashboardData, Gaps } from '../types'

// Items awaiting review can only be approved; the server enforces the lifecycle rules.
const APPROVE: ActionView = { slug: 'approve', label: 'Approve', style: 'primary' }

const GAP_GROUPS: [keyof Gaps, string][] = [
  ['reqs_without_spec', 'Requirements without a spec'],
  ['reqs_without_verification', 'Requirements without a verification'],
  ['specs_without_verification', 'Specs without a verification'],
  ['failed_verifications', 'Failed verifications'],
  ['stale', 'Stale items'],
]

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h4" component="div" sx={{ fontWeight: 700 }}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
      </CardContent>
    </Card>
  )
}

function Heading({ children }: { children: ReactNode }) {
  return (
    <Typography variant="h2" component="h2" sx={{ mt: 4, mb: 1 }}>
      {children}
    </Typography>
  )
}

function Empty({ children }: { children: ReactNode }) {
  return (
    <Typography color="text.secondary" sx={{ fontStyle: 'italic' }}>
      {children}
    </Typography>
  )
}

function DashboardView({ data, reload }: { data: DashboardData; reload: () => void }) {
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const { overview, gaps, items } = data
  const review = items.filter((i) => i.status === 'proposed' || i.status === 'stale')
  const tree = useMemo(() => buildTree(items, gapLabels(gaps)), [items, gaps])
  const gapGroups = GAP_GROUPS.filter(([key]) => gaps[key].length > 0)

  return (
    <>
      <Typography variant="h1" component="h1" gutterBottom>
        Overview
      </Typography>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        <Stat value={overview.total_items} label="items" />
        <Stat value={`${overview.coverage_percent}%`} label="requirements covered (spec + verification)" />
        <Stat value={overview.gaps} label="open gaps" />
        <Stat value={overview.stale} label="stale" />
      </Box>

      <Heading>Awaiting your review ({review.length})</Heading>
      {actionError && <ErrorAlert error={actionError} onClose={() => setActionError(null)} />}
      {review.length === 0 ? (
        <Empty>Nothing to review. Items proposed by agents appear here.</Empty>
      ) : (
        <List disablePadding>
          {review.map((item) => (
            <ListItem key={item.id} divider sx={{ gap: 1.5, flexWrap: 'wrap' }}>
              <TypeLabel type={item.type} />
              <Typography sx={{ flex: 1, minWidth: 200 }}>
                <ItemLink item={item} />
              </Typography>
              <StatusChip status={item.status} />
              <ActionButtons
                itemId={item.id}
                actions={[APPROVE]}
                size="small"
                onDone={() => {
                  setActionError(null)
                  reload()
                }}
                onError={setActionError}
              />
            </ListItem>
          ))}
        </List>
      )}

      <Heading>Gaps ({overview.gaps})</Heading>
      {gapGroups.length === 0 ? (
        <Empty>No traceability gaps.</Empty>
      ) : (
        <Stack spacing={1.5}>
          {gapGroups.map(([key, title]) => (
            <Box key={key}>
              <Typography component="span" sx={{ fontWeight: 600 }}>
                {title}:{' '}
              </Typography>
              {gaps[key].map((id) => (
                <Chip
                  key={id}
                  size="small"
                  label={id}
                  component={RouterLink}
                  to={`/items/${id}`}
                  clickable
                  sx={{ mr: 0.5 }}
                />
              ))}
            </Box>
          ))}
        </Stack>
      )}

      <Heading>Traceability tree</Heading>
      {tree.length === 0 ? (
        <Empty>
          No items yet. Run <code>specheap mcp</code> and let an agent create the first epic.
        </Empty>
      ) : (
        <Tree nodes={tree} />
      )}
    </>
  )
}

export default function DashboardPage() {
  const { data, error, loading, reload } = useApi(api.dashboard, [])
  if (error) return <ErrorAlert error={error} />
  if (!data) return loading ? <CircularProgress aria-label="Loading" /> : null
  return <DashboardView data={data} reload={reload} />
}
