import type { components } from '@/api/schema'
import type { graphNodes } from '@/design/tokens'

export type GraphNode = components['schemas']['GraphNode']
export type NodeType = components['schemas']['DictionaryTable']
export type RelationType = components['schemas']['DictionaryRelation']
export type GraphResponse = components['schemas']['GraphRead']
export type GraphLayout = 'fcose' | 'dagre'
export interface PresentationNode {
  id: string
  label: string
  type: keyof typeof graphNodes
}
export interface GraphElements {
  nodes: PresentationNode[]
  edges: { id: string, source: string, target: string, type: string }[]
}
export const nodeTypes: NodeType[] = [
  'lemma',
  'lexeme',
  'sense',
  'morpheme',
  'sentence',
  'passage',
  'tag',
]
export const relationTypes: RelationType[] = [
  'has_lexeme',
  'has_sense',
  'composed_of',
  'derives_to',
  'relates_to',
  'member_of',
  'contains',
  'used_in',
  'part_of',
]

export function presentNode(node: GraphNode): PresentationNode {
  if (!node.id || !nodeTypes.includes(node.table))
    throw new Error('Invalid graph node')
  let label: string
  switch (node.table) {
    case 'lemma':
    case 'morpheme':
    case 'sentence':
      label = node.fields.text
      break
    case 'lexeme':
      label = node.fields.pos
      break
    case 'sense':
      label = node.fields.definition
      break
    case 'tag':
      label = node.fields.name
      break
    case 'passage':
      label = node.fields.title
      break
  }
  if (typeof label !== 'string')
    throw new TypeError('Invalid graph label')
  return {
    id: node.id,
    label,
    type: node.table === 'lemma' && node.fields.kind === 'phrase'
      ? 'phrase'
      : node.table,
  }
}

export function presentGraph(graph: {
  nodes: GraphResponse['nodes']
  edges: (Pick<GraphResponse['edges'][number], 'id' | 'start' | 'end' | 'table'> & {
    fields: Pick<GraphResponse['edges'][number]['fields'], 'type'>
  })[]
}): GraphElements {
  if (graph.nodes.length > 300)
    throw new Error('Graph exceeds limit')
  const nodes = graph.nodes.map(presentNode)
  const ids = new Set(nodes.map(node => node.id))
  const edges = graph.edges.map((edge) => {
    if (!edge.id || ids.has(edge.id) || !ids.has(edge.start) || !ids.has(edge.end) || !relationTypes.includes(edge.table))
      throw new Error('Invalid graph edge')
    return {
      id: edge.id,
      source: edge.start,
      target: edge.end,
      type: edge.fields.type ?? edge.table,
    }
  })
  if (ids.size !== nodes.length || new Set(edges.map(edge => edge.id)).size !== edges.length)
    throw new Error('Duplicate graph identity')
  return { nodes, edges }
}
