import { describe, expect, it, vi } from 'vitest'
import { ApiError, api } from '../api'
import type { Gaps, Item } from '../types'
import { buildTree, defaultExpanded, expandableIds, filterTree, gapLabels, verificationStats, visibleRows } from './tree'

function item(id: string, type: Item['type'], parent: string | null = null): Item {
  return {
    id,
    type,
    title: id,
    status: 'draft',
    parent,
    body: '',
    satisfies: [],
    verifies: [],
    result: null,
    evidence: '',
    run_ref: null,
    revision: 'r',
  }
}

const noGaps: Gaps = {
  reqs_without_spec: [],
  reqs_without_verification: [],
  specs_without_verification: [],
  stale: [],
  failed_verifications: [],
}

describe('buildTree', () => {
  it('nests items under their parents and keeps order', () => {
    const items = [
      item('EPIC-001', 'epic'),
      item('FEAT-001', 'feature', 'EPIC-001'),
      item('REQ-001', 'req', 'FEAT-001'),
      item('REQ-002', 'req', 'FEAT-001'),
    ]
    const tree = buildTree(items)
    expect(tree.map((n) => n.item.id)).toEqual(['EPIC-001'])
    expect(tree[0].children[0].children.map((n) => n.item.id)).toEqual(['REQ-001', 'REQ-002'])
  })

  it('treats items whose parent is missing as roots', () => {
    const tree = buildTree([item('REQ-001', 'req', 'FEAT-404')])
    expect(tree.map((n) => n.item.id)).toEqual(['REQ-001'])
  })

  it('attaches gap badges', () => {
    const labels = gapLabels({ ...noGaps, reqs_without_spec: ['REQ-001'], reqs_without_verification: ['REQ-001'] })
    const [node] = buildTree([item('REQ-001', 'req')], labels)
    expect(node.badges).toEqual(['no spec', 'no verification'])
  })
})

function sample(): Item[] {
  return [
    item('EPIC-001', 'epic'),
    { ...item('FEAT-001', 'feature', 'EPIC-001'), title: 'Login' },
    { ...item('REQ-001', 'req', 'FEAT-001'), title: 'Lock account' },
    { ...item('REQ-002', 'req', 'FEAT-001'), title: 'Reset password', status: 'approved' },
    { ...item('SPEC-001', 'spec', 'REQ-001'), title: 'Counter' },
    { ...item('VER-001', 'verification', 'REQ-001'), result: 'pass', verifies: ['SPEC-001'] },
    { ...item('VER-002', 'verification', 'REQ-001'), result: 'fail' },
    item('VER-003', 'verification', 'REQ-002'),
  ]
}

describe('verificationStats', () => {
  it('counts results for parents and linked targets', () => {
    const stats = verificationStats(sample())
    expect(stats.get('REQ-001')).toEqual({ total: 2, pass: 1, fail: 1 })
    expect(stats.get('SPEC-001')).toEqual({ total: 1, pass: 1, fail: 0 })
    expect(stats.get('REQ-002')).toEqual({ total: 1, pass: 0, fail: 0 })
    expect(stats.has('FEAT-001')).toBe(false)
  })

  it('does not count a verification twice when it links to its own parent', () => {
    const items = [item('REQ-001', 'req'), { ...item('VER-001', 'verification', 'REQ-001'), verifies: ['REQ-001'] }]
    expect(verificationStats(items).get('REQ-001')?.total).toBe(1)
  })

  it('attaches stats to tree nodes', () => {
    const items = sample()
    const tree = buildTree(items, new Map(), verificationStats(items))
    const req = tree[0].children[0].children[0]
    expect(req.item.id).toBe('REQ-001')
    expect(req.stats).toEqual({ total: 2, pass: 1, fail: 1 })
  })
})

describe('filterTree', () => {
  const tree = () => buildTree(sample())
  const ids = (nodes: ReturnType<typeof tree>): string[] =>
    nodes.flatMap((n) => [n.item.id, ...ids(n.children)])

  it('returns everything when no filter is active', () => {
    const nodes = tree()
    expect(filterTree(nodes, { query: '  ', statuses: new Set() })).toBe(nodes)
  })

  it('keeps matches together with the ancestors that lead to them', () => {
    const result = filterTree(tree(), { query: 'counter', statuses: new Set() })
    expect(ids(result)).toEqual(['EPIC-001', 'FEAT-001', 'REQ-001', 'SPEC-001'])
  })

  it('matches by id, case-insensitively', () => {
    expect(ids(filterTree(tree(), { query: 'req-002', statuses: new Set() }))).toEqual([
      'EPIC-001',
      'FEAT-001',
      'REQ-002',
    ])
  })

  it('filters by status and combines with the query', () => {
    expect(ids(filterTree(tree(), { query: '', statuses: new Set(['approved']) }))).toEqual([
      'EPIC-001',
      'FEAT-001',
      'REQ-002',
    ])
    expect(filterTree(tree(), { query: 'lock', statuses: new Set(['approved']) })).toEqual([])
  })
})

describe('expansion', () => {
  it('opens epics and features by default but not requirements', () => {
    const nodes = buildTree(sample())
    expect([...defaultExpanded(nodes)].sort()).toEqual(['EPIC-001', 'FEAT-001'])
  })

  it('lists every node that can be expanded', () => {
    expect(expandableIds(buildTree(sample())).sort()).toEqual(['EPIC-001', 'FEAT-001', 'REQ-001', 'REQ-002'])
  })

  it('flattens only the visible rows with their depth', () => {
    const nodes = buildTree(sample())
    const rows = visibleRows(nodes, defaultExpanded(nodes))
    expect(rows.map((r) => [r.node.item.id, r.depth])).toEqual([
      ['EPIC-001', 0],
      ['FEAT-001', 1],
      ['REQ-001', 2],
      ['REQ-002', 2],
    ])
    const all = visibleRows(nodes, new Set(expandableIds(nodes)))
    expect(all).toHaveLength(8)
  })
})

describe('api', () => {
  it('turns error payloads into ApiError with code and hint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Item REQ-9 does not exist.', hint: 'Use list_items.' } }), {
          status: 404,
        }),
      ),
    )
    await expect(api.item('REQ-9')).rejects.toMatchObject({
      name: 'ApiError',
      code: 'NOT_FOUND',
      status: 404,
      hint: 'Use list_items.',
    })
    vi.unstubAllGlobals()
  })

  it('reports an unreachable server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))
    const error = await api.dashboard().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('NETWORK_ERROR')
    vi.unstubAllGlobals()
  })
})
