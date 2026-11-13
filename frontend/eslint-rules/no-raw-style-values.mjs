import postcss from 'postcss'

const exception = /^token-exception:\s*\S/
const leadingException = /\/\*\s*token-exception:\s*(?!\*\/)\S(?:(?!\*\/)[\s\S])*?\*\/\s*$/
const forbidden = /#[\da-f]{8}(?![\da-f])|#[\da-f]{6}(?![\da-f])|#[\da-f]{4}(?![\da-f])|#[\da-f]{3}(?![\da-f])|(?<![\w-])rgba?\s*\(|(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?px(?![\w-])/i
const dimension = /^(?:width|height|minWidth|maxWidth|minHeight|maxHeight|top|right|bottom|left|inset|margin|padding|gap|rowGap|columnGap|fontSize|letterSpacing|wordSpacing|border(?:Width|Radius|TopWidth|RightWidth|BottomWidth|LeftWidth)|outline(?:Width|Offset)|translate|flexBasis)(?:Top|Right|Bottom|Left|Inline|Block|InlineStart|InlineEnd|BlockStart|BlockEnd)?$/i

function findForbidden(value) {
  const withoutNonValues = value
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/url\((?:[^()"']|"[^"]*"|'[^']*')*\)/gi, ' ')
    .replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, ' ')
  return forbidden.exec(withoutNonValues)?.[0]
}

function findForbiddenFontSize(value) {
  const cleaned = value.replace(/\/\*[\s\S]*?\*\//g, '').trim()
  return /^(?:inherit|initial|unset|revert|revert-layer|var\(\s*--pw-font-size-[\w-]+\s*\))$/i.test(cleaned)
    ? undefined
    : `font-size: ${cleaned}`
}

function findForbiddenFontShorthand(value) {
  const cleaned = value
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, ' ')
  const size = /(?<![\w.-])(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em|ex|ch|vw|vh|vmin|vmax|pt|pc|cm|mm|in|%)(?![\w-])|(?<![\w-])(?:xx-small|x-small|small|medium|large|x-large|xx-large|xxx-large|smaller|larger)(?![\w-])/i.exec(cleaned)?.[0]
  return size
    ? `font-size: ${size}`
    : undefined
}

function hasCssException(node) {
  const previous = node.prev()
  return previous?.type === 'comment' && exception.test(previous.text.trim())
}

function inspectCss(css, report, inline = false) {
  try {
    const root = postcss.parse(inline
      ? `inline { ${css} }`
      : css)
    root.walkDecls((declaration) => {
      const property = declaration.prop.toLowerCase()
      const value = findForbidden(declaration.value)
        ?? (property === 'font-size'
          ? findForbiddenFontSize(declaration.value)
          : undefined)
        ?? (property === 'font'
          ? findForbiddenFontShorthand(declaration.value)
          : undefined)
      if (value && !hasCssException(declaration))
        report(value, declaration)
    })
    root.walkAtRules((rule) => {
      const value = findForbidden(rule.params)
      if (value && !hasCssException(rule))
        report(value, rule)
    })
  }
  catch {
    report('unparseable CSS')
  }
}

function walk(node, visit, parent, dimensional = false, fontKind) {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string')
    return
  if (visit(node, parent, dimensional, fontKind) === false)
    return
  for (const [key, value] of Object.entries(node)) {
    if (key === 'parent' || key === 'loc' || key === 'range' || key === 'tokens' || key === 'comments')
      continue
    let childIsDimensional = dimensional
    let childFontKind = fontKind
    if (node.type === 'Property' && key === 'value') {
      const property = String(propertyName(node) ?? '').replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())
      childIsDimensional = dimension.test(property)
      childFontKind = property.toLowerCase() === 'fontsize'
        ? 'size'
        : property.toLowerCase() === 'font'
          ? 'shorthand'
          : undefined
    }
    if ((node.type === 'ConditionalExpression' && key === 'test') || node.type === 'CallExpression') {
      childIsDimensional = false
      childFontKind = undefined
    }
    if (Array.isArray(value))
      value.forEach(child => walk(child, visit, node, childIsDimensional, childFontKind))
    else
      walk(value, visit, node, childIsDimensional, childFontKind)
  }
}

function staticValue(node) {
  if (node.type === 'Literal' && (typeof node.value === 'string' || typeof node.value === 'number'))
    return node.value
  if (node.type === 'TemplateLiteral' && node.expressions.length === 0)
    return node.quasis[0].value.cooked
  if (node.type === 'UnaryExpression' && (node.operator === '-' || node.operator === '+')) {
    const value = staticValue(node.argument)
    if (typeof value === 'number') {
      return node.operator === '-'
        ? -value
        : value
    }
  }
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    const left = staticValue(node.left)
    const right = staticValue(node.right)
    if (left != null && right != null)
      return left + right
  }
  return undefined
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
    messages: {
      raw: 'Use a design token instead of {{value}}, or add a token-exception comment with a reason.',
    },
  },
  create(context) {
    const source = context.sourceCode
    const services = source.parserServices

    function report(node, value) {
      context.report({
        node,
        messageId: 'raw',
        data: { value },
      })
    }

    function inspectStyleExpression(expression, attribute) {
      walk(expression, (node, parent, dimensional, fontKind) => {
        if (parent?.type === 'Property' && parent.key === node && !parent.computed)
          return false

        const before = source.text.slice(attribute.range[0], node.range?.[0])
        const excepted = leadingException.test(before)
        if (excepted && parent?.type === 'Property' && parent.value === node)
          return false
        const value = staticValue(node)
        if (typeof value === 'string') {
          if (!excepted) {
            if (/^\s*(?:\/\*[\s\S]*?\*\/\s*)?[\w-]+\s*:/.test(value)) {
              inspectCss(value, forbiddenValue => report(node, forbiddenValue), true)
            }
            else {
              const invalid = findForbidden(value)
                ?? (fontKind === 'size'
                  ? findForbiddenFontSize(value)
                  : undefined)
                ?? (fontKind === 'shorthand'
                  ? findForbiddenFontShorthand(value)
                  : undefined)
              if (invalid)
                report(node, invalid)
            }
          }
          return false
        }
        if (typeof value === 'number' && dimensional) {
          if (!excepted)
            report(node, `${value} (implicit px)`)
          return false
        }

        if (node.type === 'TemplateLiteral') {
          const combined = node.quasis.map(part => part.value.cooked ?? '').join('0')
          const forbiddenValue = findForbidden(combined)
          if (forbiddenValue && !excepted)
            report(node, forbiddenValue)
        }
      })
    }

    function inspectAttribute(attribute) {
      if (!attribute.directive && attribute.key.name === 'style' && attribute.value) {
        inspectCss(attribute.value.value, value => report(attribute, value), true)
        return
      }
      if (!attribute.directive || attribute.key.name.name !== 'bind' || !attribute.value?.expression)
        return
      if (attribute.key.argument?.name === 'style') {
        inspectStyleExpression(attribute.value.expression, attribute)
      }
      else if (!attribute.key.argument && attribute.value.expression.type === 'ObjectExpression') {
        for (const property of attribute.value.expression.properties) {
          if (propertyName(property) === 'style')
            inspectStyleExpression(property.value, attribute)
        }
      }
    }

    if (!services.defineTemplateBodyVisitor)
      return {}

    return services.defineTemplateBodyVisitor(
      { VAttribute: inspectAttribute },
      {
        Program() {
          const fragment = services.getDocumentFragment()
          for (const block of fragment?.children ?? []) {
            if (block.type !== 'VElement' || block.name !== 'style' || !block.endTag)
              continue
            const start = block.startTag.range[1]
            const css = source.text.slice(start, block.endTag.range[0])
            inspectCss(css, (value, cssNode) => {
              const index = start + (cssNode?.source?.start?.offset ?? 0)
              context.report({
                loc: source.getLocFromIndex(index),
                messageId: 'raw',
                data: { value },
              })
            })
          }
        },
      },
    )
  },
}
