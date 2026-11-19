// Mirrors the JSON returned by the Python API (see specheap/core/schemas.py and web/app.py).

export type ItemType = 'epic' | 'feature' | 'req' | 'spec' | 'verification'
export type Status = 'draft' | 'proposed' | 'approved' | 'implemented' | 'verified' | 'stale'
export type VerificationResult = 'pass' | 'fail' | 'skipped'

export interface Item {
  id: string
  type: ItemType
  title: string
  status: Status
  parent: string | null
  body: string
  satisfies: string[]
  verifies: string[]
  result: VerificationResult | null
  evidence: string
  run_ref: string | null
  revision: string
}

export interface Overview {
  total_items: number
  by_type: Record<string, number>
  by_status: Record<string, number>
  coverage_percent: number
  gaps: number
  stale: number
}

export interface Gaps {
  reqs_without_spec: string[]
  reqs_without_verification: string[]
  specs_without_verification: string[]
  stale: string[]
  failed_verifications: string[]
}

export interface Dashboard {
  overview: Overview
  gaps: Gaps
  items: Item[]
}

export interface ActionView {
  slug: string
  label: string
  style: 'primary' | 'secondary'
}

export interface ItemDetail {
  item: Item
  ancestors: Item[]
  children: Item[]
  downstream: Item[]
  targets: Item[]
  actions: ActionView[]
}
