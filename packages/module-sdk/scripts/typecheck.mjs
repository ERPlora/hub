// Regression for ERPlora/hub#2086. The SDK test suite runs with `--experimental-transform-types`,
// which STRIPS types instead of checking them, so a test that only asserts a type (hub#2069: a
// recipe grant announces its `reason`) stayed green when the type vanished. This script runs
// `tsc --noEmit` over the public entry point and every test file, so a type-only regression fails
// loud instead of getting stripped away silently.
import { execFileSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { TSC_OPTIONS, tscBin } from './tsc-options.mjs'

const packageDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

// `src/*.test.ts`, sorted, so a test file added tomorrow is covered without touching this script.
const testFiles = readdirSync(resolve(packageDir, 'src'))
  .filter((name) => name.endsWith('.test.ts'))
  .sort()
  .map((name) => `src/${name}`)

if (testFiles.length === 0) {
  console.error('No `src/*.test.ts` files found: the typecheck would silently cover nothing.')
  process.exit(1)
}

try {
  execFileSync(
    tscBin(packageDir),
    ['--noEmit', ...TSC_OPTIONS, '--types', 'node', 'src/index.ts', ...testFiles],
    { cwd: packageDir, stdio: 'inherit' },
  )
} catch (error) {
  process.exit(typeof error.status === 'number' ? error.status : 1)
}
