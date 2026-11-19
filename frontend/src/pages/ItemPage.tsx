import CircularProgress from '@mui/material/CircularProgress'
import Breadcrumbs from '@mui/material/Breadcrumbs'
import Chip from '@mui/material/Chip'
import Link from '@mui/material/Link'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { api } from '../api'
import type { ApiError } from '../api'
import ActionButtons from '../components/ActionButtons'
import ErrorAlert from '../components/ErrorAlert'
import ItemList from '../components/ItemList'
import StatusChip from '../components/StatusChip'
import { useApi } from '../hooks/useApi'
import type { Item, ItemDetail } from '../types'

const RESULT_COLORS = { pass: 'success', fail: 'error', skipped: 'default' } as const

function Block({ children }: { children: string }) {
  // React escapes text, so user-provided content is never interpreted as HTML.
  return (
    <Paper
      variant="outlined"
      component="pre"
      sx={{ m: 0, p: 2, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'ui-monospace, Consolas, monospace', fontSize: '0.9rem' }}
    >
      {children}
    </Paper>
  )
}

function Heading({ children }: { children: string }) {
  return (
    <Typography variant="h2" component="h2" sx={{ mt: 4, mb: 1 }}>
      {children}
    </Typography>
  )
}

function VerificationResult({ item }: { item: Item }) {
  return (
    <>
      <Heading>Latest result</Heading>
      {item.result ? (
        <Stack spacing={1} sx={{ alignItems: 'flex-start' }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip size="small" color={RESULT_COLORS[item.result]} label={item.result} />
            {item.run_ref && <Typography color="text.secondary">run: {item.run_ref}</Typography>}
          </Stack>
          {item.evidence && <Block>{item.evidence}</Block>}
        </Stack>
      ) : (
        <Typography color="text.secondary" sx={{ fontStyle: 'italic' }}>
          No result reported yet.
        </Typography>
      )}
    </>
  )
}

function ItemView({ detail, onChange }: { detail: ItemDetail; onChange: (detail: ItemDetail) => void }) {
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const { item, ancestors, children, downstream, targets, actions } = detail

  return (
    <>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/" underline="hover" color="inherit">
          Overview
        </Link>
        {ancestors.map((a) => (
          <Link key={a.id} component={RouterLink} to={`/items/${a.id}`} underline="hover" color="inherit">
            {a.id}
          </Link>
        ))}
        <Typography color="text.primary">{item.id}</Typography>
      </Breadcrumbs>

      {actionError && <ErrorAlert error={actionError} onClose={() => setActionError(null)} />}

      <Typography variant="overline" color="text.secondary">
        {item.type}
      </Typography>
      <Stack direction="row" spacing={1.5} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="h1" component="h1">
          {item.id}: {item.title}
        </Typography>
        <StatusChip status={item.status} />
      </Stack>

      <Stack direction="row" spacing={3} useFlexGap sx={{ my: 1.5, color: 'text.secondary', flexWrap: 'wrap' }}>
        <span>
          parent:{' '}
          {item.parent ? (
            <Link component={RouterLink} to={`/items/${item.parent}`}>
              {item.parent}
            </Link>
          ) : (
            'none'
          )}
        </span>
        <span>
          revision: <code>{item.revision}</code>
        </span>
      </Stack>

      {actions.length > 0 && (
        <div style={{ margin: '16px 0' }}>
          <ActionButtons
            itemId={item.id}
            actions={actions}
            onDone={(next) => {
              setActionError(null)
              onChange(next)
            }}
            onError={setActionError}
          />
        </div>
      )}

      <Heading>Description</Heading>
      {item.body ? (
        <Block>{item.body}</Block>
      ) : (
        <Typography color="text.secondary" sx={{ fontStyle: 'italic' }}>
          No description.
        </Typography>
      )}

      {item.type === 'verification' && <VerificationResult item={item} />}

      <ItemList title="Links to" items={targets} />
      <ItemList title="Children" items={children} />
      <ItemList title="Downstream items" items={downstream} />
    </>
  )
}

export default function ItemPage() {
  const { id = '' } = useParams()
  const { data, error, loading, setData } = useApi(() => api.item(id), [id])

  if (error) {
    return (
      <>
        <ErrorAlert error={error} />
        <Link component={RouterLink} to="/">
          Back to overview
        </Link>
      </>
    )
  }
  if (!data) return loading ? <CircularProgress aria-label="Loading" /> : null
  return <ItemView detail={data} onChange={setData} />
}
