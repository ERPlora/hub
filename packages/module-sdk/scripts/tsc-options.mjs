// Fixed compiler options, written here and not in a `tsconfig.json`: the snapshot has to be
// byte-identical wherever it runs, and a config file is something another tool could tune.
//
// Shared base for every `tsc` invocation in this package (`contract-check.mjs`, `typecheck.mjs`):
// the flags that decide how TypeScript reads the source. `contract-check.mjs` adds the
// declaration-emitting flags on top; `typecheck.mjs` adds `--noEmit` instead.
import { join } from 'node:path'

export const TSC_OPTIONS = [
  '--allowImportingTsExtensions',
  '--target', 'ES2022',
  '--module', 'ESNext',
  '--moduleResolution', 'Bundler',
  '--strict',
  '--skipLibCheck',
  '--lib', 'ES2022,DOM,DOM.Iterable',
]

/** The package-local `tsc` binary, so every caller runs the same pinned compiler. */
export function tscBin(packageDir) {
  return join(packageDir, 'node_modules/.bin', process.platform === 'win32' ? 'tsc.cmd' : 'tsc')
}
