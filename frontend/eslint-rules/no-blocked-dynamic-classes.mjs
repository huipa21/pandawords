import { blockedUtilityReason } from '../src/design/utility-blocklist.ts'

function walk(node, visit) {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string')
    return
  visit(node)
  for (const [key, value] of Object.entries(node)) {
    if (key === 'parent' || key === 'loc' || key === 'range' || key === 'tokens' || key === 'comments')
      continue
    if (Array.isArray(value))
      value.forEach(child => walk(child, visit))
    else
      walk(value, visit)
  }
}

function propertyName(node) {
  if (node?.type !== 'Property' || node.computed)
    return undefined
  return node.key.type === 'Identifier'
    ? node.key.name
    : node.key.value
}

export default {
  meta: {
    type: 'problem',
    schema: [],
    messages: { blocked: '{{name}}: {{reason}}' },
  },
  create(context) {
    const services = context.sourceCode.parserServices
    if (!services.defineTemplateBodyVisitor)
      return {}

    function inspect(expression) {
      walk(expression, (node) => {
        const text = node.type === 'Literal' && typeof node.value === 'string'
          ? node.value
          : node.type === 'TemplateLiteral'
            ? node.quasis.map(part => part.value.cooked ?? '').join('0')
            : ''
        for (const name of text.split(/\s+/).filter(Boolean)) {
          const reason = blockedUtilityReason(name)
          if (reason) {
            context.report({
              node,
              messageId: 'blocked',
              data: { name, reason },
            })
          }
        }
      })
    }

    return services.defineTemplateBodyVisitor({
      VAttribute(attribute) {
        if (!attribute.directive || attribute.key.name.name !== 'bind' || !attribute.value?.expression)
          return
        if (attribute.key.argument?.name === 'class') {
          inspect(attribute.value.expression)
        }
        else if (!attribute.key.argument && attribute.value.expression.type === 'ObjectExpression') {
          for (const property of attribute.value.expression.properties) {
            if (propertyName(property) === 'class')
              inspect(property.value)
          }
        }
      },
    })
  },
}
