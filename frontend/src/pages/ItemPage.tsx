import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Box from '@mui/material/Box'
import Breadcrumbs from '@mui/material/Breadcrumbs'
import Card from '@mui/material/Card'
import CircularProgress from '@mui/material/CircularProgress'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Step from '@mui/material/Step'
import StepLabel from '@mui/material/StepLabel'
import Stepper from '@mui/material/Stepper'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { api } from '../api'
import type { ApiError } from '../api'
import ActionButtons from '../components/ActionButtons'
import EmptyState from '../components/EmptyState'
import ErrorAlert from '../components/ErrorAlert'
import ItemRows, { ItemLink } from '../components/ItemRow'
import ResultChip from '../components/ResultChip'
import RichText from '../components/RichText'
import SectionCard from '../components/SectionCard'
import StatusChip from '../components/StatusChip'
import TypeIcon from '../components/TypeIcon'
import { useApi } from '../hooks/useApi'
import { TYPE_LABEL, lifecycleFor } from '../lib/meta'
import { MONO } from '../theme'
import type { Item, ItemDetail } from '../types'

const CHILD_TITLE: Record<Item['type'], string> = {
  epic: 'Features',
  feature: 'Requirements',
  req: 'Specs',
  spec: 'Children',
  verification: 'Children',
}

/** Where the item is in its lifecycle. Stale items get an explanation instead of a position. */
function Lifecycle({ item }: { item: Item }) {
  if (item.status === 'stale') {
    return (
      <Alert severity="warning">
        <AlertTitle>Needs review</AlertTitle>
        Something upstream changed after this item was approved. Review it and approve it again to confirm it is still valid.
      </Alert>
    )
  }
  const steps = lifecycleFor(item.type)
  const index = Math.max(steps.indexOf(item.status), 0)
  // The last step of the lifecycle is a destination, so it is shown as completed.
  const active = index === steps.length - 1 ? steps.length : index
  return (
    <Card sx={{ px: 2, py: 2.5 }}>
      <Stepper activeStep={active} alternativeLabel>
        {steps.map((step) => (
          <Step key={step}>
            <StepLabel sx={{ '& .MuiStepLabel-label': { textTransform: 'capitalize' } }}>{step}</StepLabel>
          </Step>
        ))}
      </Stepper>
    </Card>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" component="div">
        {label}
      </Typography>
      <Box sx={{ mt: 0.25 }}>{children}</Box>
    </Box>
  )
}

function Details({ item, targets }: { item: Item; targets: Item[] }) {
  return (
    <SectionCard title="Details">
      <Stack spacing={2}>
        <Field label="Type">{TYPE_LABEL[item.type]}</Field>
        <Field label="Status">
          <StatusChip status={item.status} />
        </Field>
        <Field label="Parent">
          {item.parent ? (
            <Link component={RouterLink} to={`/items/${item.parent}`} sx={{ fontFamily: MONO }}>
              {item.parent}
            </Link>
          ) : (
            <Typography color="text.secondary">None</Typography>
          )}
        </Field>
        {targets.length > 0 && (
          <Field label={item.type === 'spec' ? 'Also satisfies' : 'Also verifies'}>
            <Stack spacing={0.5}>
              {targets.map((target) => (
                <Typography key={target.id} noWrap>
                  <ItemLink item={target} />
                </Typography>
              ))}
            </Stack>
          </Field>
        )}
        <Field label="Revision">
          <Typography sx={{ fontFamily: MONO, fontSize: '0.85rem' }}>{item.revision}</Typography>
        </Field>
      </Stack>
    </SectionCard>
  )
}

function VerificationOutcome({ item }: { item: Item }) {
  return (
    <SectionCard title="Latest result" action={<ResultChip result={item.result} size="medium" />}>
      <Stack spacing={1.5}>
        {item.run_ref && (
          <Field label="Run">
            <Typography sx={{ fontFamily: MONO, fontSize: '0.9rem' }}>{item.run_ref}</Typography>
          </Field>
        )}
        {item.evidence ? (
          <Field label="Evidence">
            <RichText text={item.evidence} />
          </Field>
        ) : (
          <Typography color="text.secondary">{item.result ? 'No evidence attached.' : 'This verification has not been run.'}</Typography>
        )}
      </Stack>
    </SectionCard>
  )
}

function ItemView({ detail, onChange }: { detail: ItemDetail; onChange: (detail: ItemDetail) => void }) {
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const { item, ancestors, children, downstream, targets, actions } = detail

  useEffect(() => {
    document.title = `${item.id} · SpecHeap`
    return () => {
      document.title = 'SpecHeap'
    }
  }, [item.id])

  // Verifications can be children or linked from elsewhere; show each once.
  const verifications = [...children, ...downstream].filter(
    (candidate, index, all) => candidate.type === 'verification' && all.findIndex((o) => o.id === candidate.id) === index,
  )
  const structural = children.filter((child) => child.type !== 'verification')
  const otherDownstream = downstream.filter((d) => d.type !== 'verification')
  const showsVerifications = item.type === 'req' || item.type === 'spec'

  return (
    <Stack spacing={3}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/" underline="hover" color="inherit">
          Overview
        </Link>
        {ancestors.map((ancestor) => (
          <Link key={ancestor.id} component={RouterLink} to={`/items/${ancestor.id}`} underline="hover" color="inherit">
            {ancestor.id}
          </Link>
        ))}
        <Typography color="text.primary">{item.id}</Typography>
      </Breadcrumbs>

      {actionError && <ErrorAlert error={actionError} onClose={() => setActionError(null)} />}

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
      >
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', minWidth: 0 }}>
          <TypeIcon type={item.type} size={44} />
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {TYPE_LABEL[item.type]} ·{' '}
              <Box component="span" sx={{ fontFamily: MONO }}>
                {item.id}
              </Box>
            </Typography>
            <Typography variant="h1" component="h1">
              {item.title}
            </Typography>
          </Box>
        </Stack>
        {actions.length > 0 && (
          <ActionButtons
            itemId={item.id}
            actions={actions}
            onDone={(next) => {
              setActionError(null)
              onChange(next)
            }}
            onError={setActionError}
          />
        )}
      </Stack>

      <Lifecycle item={item} />

      <Box
        sx={{
          display: 'grid',
          gap: 3,
          alignItems: 'start',
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 1fr) 300px' },
        }}
      >
        <Stack spacing={3}>
          <SectionCard title={item.type === 'verification' ? 'How to verify' : 'Description'}>
            {item.body ? <RichText text={item.body} ears={item.type === 'req'} /> : <Typography color="text.secondary">No description.</Typography>}
          </SectionCard>

          {item.type === 'verification' && <VerificationOutcome item={item} />}

          {showsVerifications && (
            <SectionCard
              title="Verifications"
              subtitle={verifications.length ? `${verifications.filter((v) => v.result === 'pass').length} of ${verifications.length} pass` : undefined}
              flush
            >
              {verifications.length === 0 ? (
                <EmptyState>No verifications yet. This is a traceability gap.</EmptyState>
              ) : (
                <ItemRows items={verifications} showResult />
              )}
            </SectionCard>
          )}

          {structural.length > 0 && (
            <SectionCard title={CHILD_TITLE[item.type]} subtitle={`${structural.length}`} flush>
              <ItemRows items={structural} />
            </SectionCard>
          )}

          {otherDownstream.length > 0 && (
            <SectionCard title="Downstream items" subtitle="Further down the chain" flush>
              <ItemRows items={otherDownstream} />
            </SectionCard>
          )}
        </Stack>

        <Details item={item} targets={targets} />
      </Box>
    </Stack>
  )
}

export default function ItemPage() {
  const { id = '' } = useParams()
  const { data, error, loading, setData } = useApi(() => api.item(id), [id])

  if (error) {
    return (
      <Stack spacing={2} sx={{ alignItems: 'flex-start' }}>
        <ErrorAlert error={error} />
        <Link component={RouterLink} to="/">
          Back to overview
        </Link>
      </Stack>
    )
  }
  if (!data) return loading ? <CircularProgress aria-label="Loading" /> : null
  return <ItemView detail={data} onChange={setData} />
}
