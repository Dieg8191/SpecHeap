import Inventory2 from '@mui/icons-material/Inventory2'
import PendingActions from '@mui/icons-material/PendingActions'
import ReportProblem from '@mui/icons-material/ReportProblem'
import TaskAlt from '@mui/icons-material/TaskAlt'
import Verified from '@mui/icons-material/Verified'
import type { SvgIconComponent } from '@mui/icons-material'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import LinearProgress from '@mui/material/LinearProgress'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { alpha } from '@mui/material/styles'
import { useMemo, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { api } from '../api'
import type { ApiError } from '../api'
import ActionButtons from '../components/ActionButtons'
import EmptyState from '../components/EmptyState'
import ErrorAlert from '../components/ErrorAlert'
import { ItemRow } from '../components/ItemRow'
import SectionCard from '../components/SectionCard'
import StatusBar from '../components/StatusBar'
import Tree from '../components/Tree'
import { useApi } from '../hooks/useApi'
import { GAP_GROUPS } from '../lib/meta'
import { buildTree, gapLabels, verificationStats } from '../lib/tree'
import type { ActionView, Dashboard as DashboardData } from '../types'

// Items awaiting review can only be approved; the server enforces the lifecycle rules.
const APPROVE: ActionView = { slug: 'approve', label: 'Approve', style: 'primary' }

type Tone = 'primary' | 'success' | 'warning' | 'error'

interface StatProps {
  icon: SvgIconComponent
  label: string
  value: string | number
  hint?: string
  tone?: Tone
  children?: React.ReactNode
}

function StatCard({ icon: Icon, label, value, hint, tone = 'primary', children }: StatProps) {
  return (
    <Card sx={{ p: 2.5 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box
          sx={(theme) => ({
            width: 40,
            height: 40,
            flexShrink: 0,
            display: 'grid',
            placeItems: 'center',
            borderRadius: 2,
            color: `${tone}.main`,
            bgcolor: alpha(theme.palette[tone].main, theme.palette.mode === 'dark' ? 0.16 : 0.1),
          })}
        >
          <Icon />
        </Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
          <Typography sx={{ fontSize: '1.9rem', fontWeight: 700, lineHeight: 1.2, fontVariantNumeric: 'tabular-nums' }}>
            {value}
          </Typography>
          {children}
          {hint && (
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
              {hint}
            </Typography>
          )}
        </Box>
      </Stack>
    </Card>
  )
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

function DashboardView({ data, reload }: { data: DashboardData; reload: () => void }) {
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const { overview, gaps, items } = data

  const review = items.filter((i) => i.status === 'proposed' || i.status === 'stale')
  const tree = useMemo(() => buildTree(items, gapLabels(gaps), verificationStats(items)), [items, gaps])
  const gapGroups = GAP_GROUPS.filter(([key]) => gaps[key].length > 0)

  const reqs = overview.by_type.req ?? 0
  const covered = Math.round((overview.coverage_percent / 100) * reqs)
  const proposed = overview.by_status.proposed ?? 0
  const stale = overview.by_status.stale ?? 0
  const typeSummary = [
    plural(overview.by_type.epic ?? 0, 'epic'),
    plural(overview.by_type.feature ?? 0, 'feature'),
    plural(reqs, 'req'),
    plural(overview.by_type.spec ?? 0, 'spec'),
    plural(overview.by_type.verification ?? 0, 'verification'),
  ].join(' · ')

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h1" component="h1">
          Overview
        </Typography>
        <Typography color="text.secondary">Where the specification stands and what needs a decision.</Typography>
      </Box>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' } }}>
        <StatCard icon={Inventory2} label="Items" value={overview.total_items} hint={typeSummary} />
        <StatCard
          icon={Verified}
          label="Requirement coverage"
          value={`${overview.coverage_percent}%`}
          tone="success"
          hint={`${covered} of ${plural(reqs, 'requirement')} with a spec and a verification`}
        >
          <LinearProgress
            variant="determinate"
            value={overview.coverage_percent}
            color="success"
            aria-label="Requirement coverage"
            sx={{ mt: 1, height: 6, borderRadius: 3 }}
          />
        </StatCard>
        <StatCard
          icon={ReportProblem}
          label="Open gaps"
          value={overview.gaps}
          tone={overview.gaps > 0 ? 'warning' : 'success'}
          hint={overview.gaps > 0 ? 'Missing specs, verifications or stale items' : 'Everything is traced'}
        />
        <StatCard
          icon={PendingActions}
          label="Needs review"
          value={proposed + stale}
          tone={proposed + stale > 0 ? 'error' : 'success'}
          hint={`${proposed} proposed · ${stale} stale`}
        />
      </Box>

      <SectionCard title="Status distribution" subtitle="Every item, by lifecycle status">
        <StatusBar counts={overview.by_status} />
      </SectionCard>

      <Box
        sx={{
          display: 'grid',
          gap: 3,
          alignItems: 'start',
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 1.55fr) minmax(0, 1fr)' },
        }}
      >
        <SectionCard title="Traceability tree" subtitle="Epic → Feature → Requirement → Spec → Verification" flush>
          {tree.length === 0 ? (
            <EmptyState>
              No items yet. Run <code>specheap mcp</code> and let an agent create the first epic.
            </EmptyState>
          ) : (
            <Tree nodes={tree} counts={overview.by_status} />
          )}
        </SectionCard>

        <Stack spacing={3}>
          <SectionCard
            title="Awaiting your review"
            subtitle={review.length === 0 ? 'Nothing pending' : plural(review.length, 'item')}
            flush
          >
            {actionError && (
              <Box sx={{ p: 2, pb: 0 }}>
                <ErrorAlert error={actionError} onClose={() => setActionError(null)} />
              </Box>
            )}
            {review.length === 0 ? (
              <EmptyState icon={<TaskAlt color="success" />}>All caught up. Items proposed by agents appear here.</EmptyState>
            ) : (
              review.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  action={
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
                  }
                />
              ))
            )}
          </SectionCard>

          <SectionCard title="Gaps" subtitle={overview.gaps === 0 ? 'No gaps' : plural(overview.gaps, 'gap')}>
            {gapGroups.length === 0 ? (
              <EmptyState icon={<TaskAlt color="success" />}>No traceability gaps.</EmptyState>
            ) : (
              <Stack spacing={2}>
                {gapGroups.map(([key, title]) => (
                  <Box key={key}>
                    <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.75 }}>
                      {title}{' '}
                      <Typography component="span" variant="body2" color="text.secondary">
                        ({gaps[key].length})
                      </Typography>
                    </Typography>
                    <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 0.75 }}>
                      {gaps[key].map((id) => (
                        <Chip key={id} size="small" variant="outlined" label={id} component={RouterLink} to={`/items/${id}`} clickable />
                      ))}
                    </Stack>
                  </Box>
                ))}
              </Stack>
            )}
          </SectionCard>
        </Stack>
      </Box>
    </Stack>
  )
}

export default function DashboardPage() {
  const { data, error, loading, reload } = useApi(api.dashboard, [])
  if (error) return <ErrorAlert error={error} />
  if (!data) return loading ? <CircularProgress aria-label="Loading" /> : null
  return <DashboardView data={data} reload={reload} />
}
