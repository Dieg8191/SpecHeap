import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'
import { MONO } from '../theme'

// Labels that open a line in generated item bodies ("Rationale: ...", "Pass criteria: ...").
const LABELS = [
  'Rationale',
  'Priority',
  'Goal',
  'Scope',
  'Out of scope',
  'Success metrics',
  'Pass criteria',
  'Steps',
  'Run',
  'Automated check',
  'Manual check',
]

type Block =
  | { kind: 'p'; lines: string[] }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'code'; lines: string[] }

/** Split plain text into paragraphs, lists and indented code blocks. */
function parse(text: string): Block[] {
  const blocks: Block[] = []
  let open = false // Whether the last block can still grow (no blank line since).

  const push = (kind: Block['kind'], value: string) => {
    const last = blocks[blocks.length - 1]
    if (open && last && last.kind === kind) {
      if (last.kind === 'ul' || last.kind === 'ol') last.items.push(value)
      else last.lines.push(value)
    } else if (kind === 'ul' || kind === 'ol') {
      blocks.push({ kind, items: [value] })
    } else {
      blocks.push({ kind, lines: [value] })
    }
    open = true
  }

  for (const raw of text.split('\n')) {
    const line = raw.trimEnd()
    if (line.trim() === '') {
      open = false
      continue
    }
    const bullet = /^-\s+(.*)$/.exec(line)
    const numbered = /^\d+\.\s+(.*)$/.exec(line)
    if (bullet) push('ul', bullet[1])
    else if (numbered) push('ol', numbered[1])
    else if (/^\s{2,}\S/.test(line)) push('code', line.trim())
    else push('p', line)
  }
  return blocks
}

/** Inline formatting: `code`, and EARS keywords when the text is a requirement. */
function inline(text: string, ears: boolean): ReactNode[] {
  const pattern = ears ? /(`[^`]+`)|\b(THE SYSTEM SHALL|SHALL NOT|SHALL|WHEN|WHERE|IF|THEN)\b/g : /(`[^`]+`)/g
  const out: ReactNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index))
    if (match[1]) {
      out.push(
        <Box
          key={match.index}
          component="code"
          sx={{ fontFamily: MONO, fontSize: '0.86em', px: 0.6, py: 0.1, borderRadius: 0.75, bgcolor: 'action.hover' }}
        >
          {match[1].slice(1, -1)}
        </Box>,
      )
    } else {
      out.push(
        <Box key={match.index} component="span" sx={{ fontWeight: 700, color: 'primary.main', letterSpacing: '0.01em' }}>
          {match[2]}
        </Box>,
      )
    }
    last = match.index + match[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function Line({ text, ears }: { text: string; ears: boolean }) {
  const label = LABELS.find((l) => text.startsWith(`${l}:`))
  if (!label) return <>{inline(text, ears)}</>
  return (
    <>
      <Box component="strong" sx={{ color: 'text.secondary' }}>
        {label}:
      </Box>
      {inline(text.slice(label.length + 1), false)}
    </>
  )
}

/**
 * Renders the plain-text bodies SpecHeap stores. React escapes all text, so item content is never
 * interpreted as HTML. `ears` highlights the keywords of EARS-style requirements.
 */
export default function RichText({ text, ears = false }: { text: string; ears?: boolean }) {
  return (
    <Box sx={{ '& > * + *': { mt: 1.5 }, lineHeight: 1.65, overflowWrap: 'anywhere' }}>
      {parse(text).map((block, index) => {
        if (block.kind === 'ul' || block.kind === 'ol') {
          return (
            <Box key={index} component={block.kind} sx={{ m: 0, pl: 3 }}>
              {block.items.map((item, i) => (
                <li key={i}>
                  <Line text={item} ears={ears} />
                </li>
              ))}
            </Box>
          )
        }
        if (block.kind === 'code') {
          return (
            <Box
              key={index}
              component="pre"
              sx={{ m: 0, p: 1.5, borderRadius: 1.5, bgcolor: 'action.hover', fontFamily: MONO, fontSize: '0.85rem', overflowX: 'auto' }}
            >
              {block.lines.join('\n')}
            </Box>
          )
        }
        return (
          <Typography key={index} component="p" sx={{ m: 0 }}>
            {block.lines.map((line, i) => (
              <span key={i}>
                {i > 0 && <br />}
                <Line text={line} ears={ears} />
              </span>
            ))}
          </Typography>
        )
      })}
    </Box>
  )
}
