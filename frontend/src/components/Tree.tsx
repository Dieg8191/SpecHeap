import ChevronRight from '@mui/icons-material/ChevronRight'
import ExpandMore from '@mui/icons-material/ExpandMore'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import IconButton from '@mui/material/IconButton'
import Stack from '@mui/material/Stack'
import { useState } from 'react'
import type { TreeNode } from '../lib/tree'
import { ItemLink, TypeLabel } from './ItemList'
import StatusChip from './StatusChip'

function Node({ node }: { node: TreeNode }) {
  const [open, setOpen] = useState(true)
  const hasChildren = node.children.length > 0
  return (
    <Box component="li" sx={{ listStyle: 'none' }}>
      <Stack direction="row" spacing={1} useFlexGap sx={{ py: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
        <IconButton
          size="small"
          aria-label={open ? `Collapse ${node.item.id}` : `Expand ${node.item.id}`}
          onClick={() => setOpen((value) => !value)}
          disabled={!hasChildren}
          sx={{ visibility: hasChildren ? 'visible' : 'hidden' }}
        >
          {open ? <ExpandMore fontSize="small" /> : <ChevronRight fontSize="small" />}
        </IconButton>
        <TypeLabel type={node.item.type} />
        <span>
          <ItemLink item={node.item} />
        </span>
        <StatusChip status={node.item.status} />
        {node.badges.map((label) => (
          <Chip key={label} size="small" color="error" variant="outlined" label={label} />
        ))}
      </Stack>
      {hasChildren && (
        <Collapse in={open} unmountOnExit>
          <Box component="ul" sx={{ m: 0, pl: 3, borderLeft: 1, borderColor: 'divider', ml: 1.5 }}>
            {node.children.map((child) => (
              <Node key={child.item.id} node={child} />
            ))}
          </Box>
        </Collapse>
      )}
    </Box>
  )
}

export default function Tree({ nodes }: { nodes: TreeNode[] }) {
  return (
    <Box component="ul" sx={{ m: 0, p: 0 }}>
      {nodes.map((node) => (
        <Node key={node.item.id} node={node} />
      ))}
    </Box>
  )
}
