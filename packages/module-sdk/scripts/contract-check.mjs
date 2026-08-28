// `contracts/kernel/sdk.d.ts` ≡ the public API of `@erplora/module-sdk` — ERPlora/hub#1235.
//
// Regression test for ERPlora/hub#1235. This package is the bridge every module's Web Component
// talks to the hub through: `erplora.query/command/on`, the list engine, the errors, the flows
// client. A module's `dist/*.esm.js` is published COMPILED, so removing an export here breaks
// installed modules and nothing in this repo would notice.
//
// The snapshot is the real `.d.ts`, emitted by `tsc` from `src/`. Not a hand-kept list of names:
// the whole point is that the signatures move too.
//
//   pnpm -F @erplora/module-sdk contract:check         # compara, falla con el diff
//   UPDATE_KERNEL_CONTRACT=1 pnpm -F @erplora/module-sdk contract:check   # regenera
//
// Cambiar esta superficie es una PR `kind:contract` con entrada en el decision-log
// (ADR «El Hub se CIERRA como KERNEL»).
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const packageDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const snapshot = resolve(packageDir, '../../contracts/kernel/sdk.d.ts')
const update = process.env.UPDATE_KERNEL_CONTRACT === '1'

// Fixed compiler options, written here and not in a `tsconfig.json`: the snapshot has to be
// byte-identical wherever it runs, and a config file is something another tool could tune.
const OPTIONS = [
  '--declaration',
  '--emitDeclarationOnly',
  '--removeComments',
  '--allowImportingTsExtensions',
  '--target', 'ES2022',
  '--module', 'ESNext',
  '--moduleResolution', 'Bundler',
  '--strict',
  '--skipLibCheck',
  '--lib', 'ES2022,DOM,DOM.Iterable',
]

const outDir = mkdtempSync(join(tmpdir(), 'erplora-sdk-dts-'))
let generated
try {
  execFileSync(
    process.platform === 'win32' ? 'tsc.cmd' : 'tsc',
    [...OPTIONS, '--outDir', outDir, 'src/index.ts'],
    { cwd: packageDir, stdio: 'inherit', env: { ...process.env, PATH: `${join(packageDir, 'node_modules/.bin')}:${process.env.PATH}` } },
  )
  // Every emitted file, in a stable order, each under a banner naming it: `index.d.ts` re-exports
  // from its siblings, so a snapshot of the entry alone would miss what those siblings declare.
  const files = readdirSync(outDir).filter((f) => f.endsWith('.d.ts')).sort()
  if (files.length === 0) {
    throw new Error('`tsc` no ha emitido ningún `.d.ts`: el contrato saldría vacío')
  }
  generated =
    '// API pública de `@erplora/module-sdk` — generada por `tsc --emitDeclarationOnly`,\n' +
    '// NO editar a mano. Regenerar: UPDATE_KERNEL_CONTRACT=1 pnpm -F @erplora/module-sdk contract:check\n' +
    '// Contrato del kernel: ADR «El Hub se CIERRA como KERNEL».\n' +
    files.map((f) => `\n// ── ${f} ${'─'.repeat(Math.max(0, 70 - f.length))}\n${readFileSync(join(outDir, f), 'utf8')}`).join('')
} finally {
  rmSync(outDir, { recursive: true, force: true })
}

if (update) {
  writeFileSync(snapshot, generated)
  console.log(`contracts/kernel/sdk.d.ts regenerado (${generated.split('\n').length} líneas)`)
  process.exit(0)
}

let committed
try {
  committed = readFileSync(snapshot, 'utf8')
} catch (error) {
  console.error(
    `\`contracts/kernel/sdk.d.ts\` no se puede leer (${error.code}).\n` +
      'Es parte del contrato del kernel y va COMMITEADO. Genéralo con:\n' +
      '  UPDATE_KERNEL_CONTRACT=1 pnpm -F @erplora/module-sdk contract:check',
  )
  process.exit(1)
}

if (committed === generated) {
  process.exit(0)
}

const old = new Set(committed.split('\n'))
const now = new Set(generated.split('\n'))
const added = [...now].filter((l) => !old.has(l) && l.trim())
const removed = [...old].filter((l) => !now.has(l) && l.trim())
console.error(
  '`contracts/kernel/sdk.d.ts` ya no describe la API pública de `@erplora/module-sdk`.\n' +
    `\n  AÑADIDO por el código (${added.length} línea/s):\n${added.map((l) => `    + ${l}`).join('\n') || '    (ninguna)'}\n` +
    `\n  QUE FALTA en el código (${removed.length} línea/s):\n${removed.map((l) => `    - ${l}`).join('\n') || '    (ninguna)'}\n` +
    '\nCambiar esta superficie es una PR `kind:contract` con entrada en el decision-log\n' +
    '(ADR «El Hub se CIERRA como KERNEL»). Si el cambio es el que querías, regenera y revisa el diff:\n' +
    '  UPDATE_KERNEL_CONTRACT=1 pnpm -F @erplora/module-sdk contract:check',
)
process.exit(1)
