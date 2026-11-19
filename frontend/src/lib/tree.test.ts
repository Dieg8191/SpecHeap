import { describe, expect, it, vi } from 'vitest'
import { ApiError, api } from '../api'
import type { Gaps, Item } from '../types'
import { buildTree, gapLabels } from './tree'

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
