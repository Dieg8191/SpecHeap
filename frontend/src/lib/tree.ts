import type { Gaps, Item } from '../types'

export interface TreeNode {
  item: Item
  badges: string[]
  children: TreeNode[]
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

/** Nest items under their parents, preserving the order of `items`. Orphans become roots. */
export function buildTree(items: Item[], labels: Map<string, string[]> = new Map()): TreeNode[] {
  const nodes = new Map<string, TreeNode>(
    items.map((item) => [item.id, { item, badges: labels.get(item.id) ?? [], children: [] }]),
  )
  const roots: TreeNode[] = []
  for (const item of items) {
    const node = nodes.get(item.id)!
    const parent = item.parent ? nodes.get(item.parent) : undefined
    ;(parent ? parent.children : roots).push(node)
  }
  return roots
}
