import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import { useState } from 'react'
import { ApiError, api } from '../api'
import type { ActionView, ItemDetail } from '../types'

interface Props {
  itemId: string
  actions: ActionView[]
  size?: 'small' | 'medium'
  onDone: (detail: ItemDetail) => void
  onError: (error: ApiError) => void
}

/** Lifecycle actions a human may trigger. The server enforces the rules; this only offers them. */
export default function ActionButtons({ itemId, actions, size = 'medium', onDone, onError }: Props) {
  const [busy, setBusy] = useState<string | null>(null)

  async function run(slug: string) {
    setBusy(slug)
    try {
      onDone(await api.runAction(itemId, slug))
    } catch (error) {
      onError(error instanceof ApiError ? error : new ApiError('UNKNOWN', String(error), 0))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Stack direction="row" spacing={1}>
      {actions.map((action) => (
        <Button
          key={action.slug}
          size={size}
          variant={action.style === 'primary' ? 'contained' : 'outlined'}
          disabled={busy !== null}
          onClick={() => run(action.slug)}
        >
          {busy === action.slug ? 'Working…' : action.label}
        </Button>
      ))}
    </Stack>
  )
}
