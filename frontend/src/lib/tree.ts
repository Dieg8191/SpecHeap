import type { Gaps, Item, Status } from '../types'

export interface VerificationStats {
  total: number
  pass: number
  fail: number
}

export interface TreeNode {
  item: Item
  badges: string[]
  stats: VerificationStats | null
  children: TreeNode[]
}

export interface TreeFilter {
  query: string
  statuses: ReadonlySet<Status>
}

/** Short labels shown next to items that have traceability problems. */
export function gapLabels(gaps: Gaps): Map<string, string[]> {
  const labels = new Map<string, string[]>()
  const add = (ids: string[], label: string) => {
    for (const id of ids) labels.set(id, [...(labels.get(id) ?? []), label])
  }
  add(gaps.reqs_without_spec, 'no spec')
  add(gaps.reqs_without_verification, 'no verification')
  add(gaps.specs_without_verification, 'no verification')
  add(gaps.failed_verifications, 'failed')
  return labels
}

/** Verification results per requirement or spec, counting both parents and `verifies` links. */
export function verificationStats(items: Item[]): Map<string, VerificationStats> {
  const stats = new Map<string, VerificationStats>()
  for (const verification of items) {
    if (verification.type !== 'verification') continue
    const targets = new Set([...(verification.parent ? [verification.parent] : []), ...verification.verifies])
    for (const target of targets) {
      const entry = stats.get(target) ?? { total: 0, pass: 0, fail: 0 }
      entry.total += 1
      if (verification.result === 'pass') entry.pass += 1
      if (verification.result === 'fail') entry.fail += 1
      stats.set(target, entry)
    }
  }
  return stats
}

/** Nest items under their parents, preserving the order of `items`. Orphans become roots. */
export function buildTree(
  items: Item[],
  labels: Map<string, string[]> = new Map(),
  stats: Map<string, VerificationStats> = new Map(),
): TreeNode[] {
  const nodes = new Map<string, TreeNode>(
    items.map((item) => [
      item.id,
      { item, badges: labels.get(item.id) ?? [], stats: stats.get(item.id) ?? null, children: [] },
    ]),
  )
  const roots: TreeNode[] = []
  for (const item of items) {
    const node = nodes.get(item.id)!
    const parent = item.parent ? nodes.get(item.parent) : undefined
    ;(parent ? parent.children : roots).push(node)
  }
  return roots
}

export function isFiltering(filter: TreeFilter): boolean {
  return filter.query.trim() !== '' || filter.statuses.size > 0
}

/** Keep nodes that match the filter, plus the ancestors needed to reach them. */
export function filterTree(nodes: TreeNode[], filter: TreeFilter): TreeNode[] {
  if (!isFiltering(filter)) return nodes
  const query = filter.query.trim().toLowerCase()
  const matches = (node: TreeNode) =>
    (query === '' || node.item.id.toLowerCase().includes(query) || node.item.title.toLowerCase().includes(query)) &&
    (filter.statuses.size === 0 || filter.statuses.has(node.item.status))
  const walk = (list: TreeNode[]): TreeNode[] =>
    list.flatMap((node) => {
      const children = walk(node.children)
      return matches(node) || children.length > 0 ? [{ ...node, children }] : []
    })
  return walk(nodes)
}

/** Ids of every node that has children. */
export function expandableIds(nodes: TreeNode[]): string[] {
  return nodes.flatMap((node) => (node.children.length > 0 ? [node.item.id, ...expandableIds(node.children)] : []))
}

/** By default epics and features are open so the tree shows the structure at a glance. */
export function defaultExpanded(nodes: TreeNode[]): Set<string> {
  const open = new Set<string>()
  const walk = (list: TreeNode[]) => {
    for (const node of list) {
      if ((node.item.type === 'epic' || node.item.type === 'feature') && node.children.length > 0) open.add(node.item.id)
      walk(node.children)
    }
  }
  walk(nodes)
  return open
}

export interface TreeRow {
  node: TreeNode
  depth: number
}

/** Flatten the tree into the rows that are currently visible. */
export function visibleRows(nodes: TreeNode[], expanded: ReadonlySet<string>, depth = 0): TreeRow[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...(expanded.has(node.item.id) ? visibleRows(node.children, expanded, depth + 1) : []),
  ])
}
