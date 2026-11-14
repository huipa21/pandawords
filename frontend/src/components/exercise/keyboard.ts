export function acceptsShortcut(event: KeyboardEvent) {
  return !event.defaultPrevented && !event.repeat && !event.isComposing
    && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey
}

export function isEditing(event: KeyboardEvent) {
  return event.target instanceof Element
    && Boolean(event.target.closest('input, textarea, select, [contenteditable="true"]'))
}
