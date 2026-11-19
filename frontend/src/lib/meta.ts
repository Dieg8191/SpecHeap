import type { ItemType, Status } from '../types'

export const TYPE_LABEL: Record<ItemType, string> = {
  epic: 'Epic',
  feature: 'Feature',
  req: 'Requirement',
  spec: 'Spec',
  verification: 'Verification',
}

/** Statuses an item moves through in order. `stale` is a side state, not a step. */
export const LIFECYCLE: Status[] = ['draft', 'proposed', 'approved', 'implemented', 'verified']
export const ALL_STATUSES: Status[] = [...LIFECYCLE, 'stale']

/** Only requirements and specs are implemented and verified; others stop at approved. */
export function lifecycleFor(type: ItemType): Status[] {
  return type === 'req' || type === 'spec' ? LIFECYCLE : LIFECYCLE.slice(0, 3)
}

export type PaletteKey = 'warning' | 'info' | 'secondary' | 'success' | 'error' | 'grey'

export const STATUS_COLOR: Record<Status, PaletteKey> = {
  draft: 'grey',
  proposed: 'warning',
  approved: 'info',
  implemented: 'secondary',
  verified: 'success',
  stale: 'error',
}

export const GAP_GROUPS = [
  ['reqs_without_spec', 'Requirements without a spec'],
  ['reqs_without_verification', 'Requirements without a verification'],
  ['specs_without_verification', 'Specs without a verification'],
  ['failed_verifications', 'Failed verifications'],
  ['stale', 'Stale items'],
] as const
