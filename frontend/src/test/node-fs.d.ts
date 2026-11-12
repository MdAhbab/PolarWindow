/**
 * The one piece of Node the unit tests use: reading a stylesheet as text
 * (lib/motion.test.tsx; vitest leaves CSS imports empty). The app's own types
 * are the browser's, so this declares only that call.
 */
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string
}
