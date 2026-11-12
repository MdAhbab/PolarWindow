/**
 * The words rule (clarity plan, Part F): no long dash, no model or vendor
 * name, and none of the banned words in anything that can reach the screen:
 * quoted strings and JSX text in the app's source, comments left out. Model
 * names may appear only in the run log and the answer's Technical details,
 * which read them from the server, never from a string here.
 */
import { describe, expect, it } from 'vitest'

const files = import.meta.glob(['../**/*.{ts,tsx}', '!../**/*.test.*', '!../lib/api/schema.ts', '!../**/__fixtures__/**', '!../**/*.d.ts'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const BANNED = /\b(best|safest|recommended|score|likely)\b/i
const MODEL = /gemini|gpt-|claude|openai|anthropic/i

function withoutComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, (m) => '\n'.repeat(m.split('\n').length - 1)).replace(/(?<![:'"`])\/\/[^\n]*/g, '')
}

function onScreen(line: string): string[] {
  return line.match(/'[^'\n]*'|"[^"\n]*"|`[^`\n]*`|>[^<>{}\n]+</g) ?? []
}

describe('words on screen', () => {
  const found: string[] = []
  for (const [path, src] of Object.entries(files)) {
    withoutComments(src)
      .split('\n')
      .forEach((line, i) => {
        for (const part of onScreen(line)) {
          const why = [
            /[–—]/.test(part) && 'long dash',
            MODEL.test(part) && 'model name',
            !line.includes('className') && BANNED.test(part) && `"${BANNED.exec(part)?.[0]}"`,
          ].filter(Boolean)
          if (why.length) found.push(`${path}:${i + 1} ${why.join(', ')}: ${part.slice(0, 80)}`)
        }
      })
  }

  it('reads every source file', () => {
    expect(Object.keys(files).length).toBeGreaterThan(100)
  })

  it('has no long dash, model name or banned word', () => {
    expect(found).toEqual([])
  })
})
