import { Children, cloneElement, isValidElement, type ReactNode } from 'react'
import { bind } from './format'

/**
 * `bind` (format.ts) for something about to be drawn: every piece of text in
 * it, however deep inside its own elements, has its figures held together, so
 * a line never ends between a number and its margin or unit, inside a date, or
 * between a time and "UTC". Elements keep their keys, props and order; only
 * plain spaces inside those figures become non-breaking ones, so the words,
 * the order and what a screen reader says do not change.
 *
 * Applied where text is drawn (the answer sentence, a page's lede, a key
 * number's lines), never to what the formatters return: other code takes
 * those strings apart, and the tests compare them.
 */
export function bindNode(node: ReactNode): ReactNode {
  if (typeof node === 'string') return bind(node)
  if (node === null || node === undefined || typeof node === 'boolean' || typeof node === 'number') return node
  if (Array.isArray(node)) return Children.map(node, (c) => bindNode(c))
  if (isValidElement<{ children?: ReactNode }>(node)) {
    const kids = node.props.children
    if (kids === undefined || kids === null) return node
    return cloneElement(node, undefined, bindNode(kids))
  }
  return node
}
