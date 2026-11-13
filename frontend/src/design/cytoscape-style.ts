import { graphEdges, graphNodes } from './tokens'

export interface CytoscapeStyleRule {
  selector: string
  style: Record<string, string>
}

export function createCytoscapeStyle(element: Element = document.documentElement): CytoscapeStyleRule[] {
  const computed = getComputedStyle(element)
  const value = (name: string) => computed.getPropertyValue(`--pw-${name}`).trim()

  const nodes = Object.entries(graphNodes).map(([name, node]) => ({
    selector: `node[type = "${name}"]`,
    style: {
      'background-color': value(`node-${name}`),
      'shape': node.shape,
    },
  }))
  const edges = Object.entries(graphEdges).map(([name, edge]) => ({
    selector: `edge[type = "${name}"]`,
    style: {
      'line-color': value(`edge-${name}`),
      'target-arrow-color': value(`edge-${name}`),
      'line-style': edge.line === 'thin'
        ? 'solid'
        : edge.line,
      'target-arrow-shape': 'arrow' in edge && edge.arrow
        ? 'triangle'
        : 'none',
    },
  }))

  return [
    {
      selector: 'node',
      style: {
        'color': value('color-text'),
        'font-family': value('font-sans'),
      },
    },
    {
      selector: 'edge',
      style: {
        'line-color': value('edge-default'),
      },
    },
    ...nodes,
    ...edges,
  ]
}
