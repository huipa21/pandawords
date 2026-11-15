import type { StylesheetJson } from 'cytoscape'
import type { ThemeMode } from '@/design/tokens'
import { graphEdges, graphMetrics, graphNodes, themes } from '@/design/tokens'

export function graphStyle(mode: ThemeMode): StylesheetJson {
  const theme = themes[mode]
  return [
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'width': graphMetrics.nodeSize,
        'height': graphMetrics.nodeSize,
        'color': theme.colors.text,
        'font-size': graphMetrics.labelSize,
        'text-wrap': 'ellipsis',
        'text-max-width': graphMetrics.labelWidth,
        'text-valign': 'bottom',
      },
    },
    ...Object.entries(graphNodes).map(([type, node]) => ({
      selector: `node[type = "${type}"]`,
      style: { 'shape': node.shape, 'background-color': theme.nodes[type as keyof typeof graphNodes] },
    })),
    {
      selector: 'edge',
      style: {
        'width': graphMetrics.edgeWidth,
        'line-color': theme.edges.default,
        'target-arrow-color': theme.edges.default,
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
      },
    },
    ...Object.entries(graphEdges).map(([type, edge]) => ({
      selector: `edge[type = "${type}"]`,
      style: {
        'line-color': theme.edges[type as keyof typeof graphEdges],
        'target-arrow-color': theme.edges[type as keyof typeof graphEdges],
        'line-style': edge.line === 'thin'
          ? 'solid'
          : edge.line,
      },
    })),
    {
      selector: 'node:selected, node.focus',
      style: {
        'border-color': theme.colors.focus,
        'border-width': graphMetrics.borderWidth,
        'width': graphMetrics.focusSize,
        'height': graphMetrics.focusSize,
      },
    },
  ] as StylesheetJson
}
