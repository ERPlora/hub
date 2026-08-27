// Copies the installed modules' artifacts (module.json + dist/<id>.esm.js) into
// public/modules/** so the shell can load them at runtime with dynamic import()
// (Vite serves public/ at the root, in dev and in build).
//
// In production this does NOT exist: the runtime (crates/server) serves the modules downloaded
// from the marketplace. This is only the bridge for the dev web shell. ARQUITECTURA.md §4.
import { mkdirSync, copyFileSync, existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DST = join(HERE, 'public/modules');

// POS batch (Stencil→Lit, 2026-06-07): the modules the dev shell loads at runtime.
// In prod this does not exist (the runtime serves the marketplace modules) — this is the dev bridge.
//
// ⚠️ A module MISSING from this list is skipped in SILENCE (the `did you build it?` warning only
// fires for one that is listed and has no `module.json`), and then the bench contradicts itself:
// the runtime reports the module installed while the shell answers «no se pudo cargar el módulo».
// That is what happened to `flows`, the 25th (pm#110) — added below, and pinned by a test.
//
// A RETIRED module is the mirror case and is deliberately absent: `invoice_series` was retired by
// ADR-0369 (invoice_series#20) because fiscal numbering has a single owner, `invoice`. Listing it
// here brought back the duplicated «Tu numeración de facturas» setup step on every local bench.
// Its absence is pinned by a test too, so nobody re-adds it by copying an old list.
export const MODULES = [
  'appointments', 'cart_checkout', 'cash_register', 'customers', 'flows', 'inventory',
  'invoice', 'kitchen', 'online_booking',
  'payment_gateways', 'payments', 'pricing', 'reservations',
  'printing', 'sales', 'schedules', 'services', 'staff', 'tables',
  'tasks', 'taxes', 'tickets', 'verifactu', 'whatsapp_inbox',
];

// Main checkout of THIS repo, via the git common dir (absolute even from a worktree).
// Returns null outside a git checkout (e.g. the Docker image build) — callers fall through.
function defaultGitCommonDir(startDir) {
  try {
    const out = execFileSync(
      'git',
      ['-C', startDir, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
    ).trim();
    return out || null;
  } catch {
    return null;
  }
}

// Source of truth for dev modules: the toolkit's dev workspace at the MONOREPO root
// (ERPlora/modules-workspace/modules/<id>/, each its own git repo, managed by
// @erplora/module-toolkit). hub/modules/ is reserved for runtime-INSTALLED modules.
//
// hub#787: the path used to be hardcoded relative to this file, so `pnpm dev` from a git
// worktree booted a hub with zero modules. Resolution order (same shape as the pre-push hook's
// `resolve_modules_dir`, and the hub#643 precedent for `blueprints/`):
//   1. ERPLORA_MODULES_DIR (the escape hatch the cargo e2e already document)
//   2. HUB_MODULES_DIR (the var scripts/dev.mjs exports for the runtime)
//   3. walk up from this file until `modules-workspace/modules` appears (main checkout)
//   4. derive the main checkout from the git common dir (worktrees live elsewhere)
// Returns { dir, tried }: `dir` is null when nothing was found; `tried` feeds a truthful warning.
export function resolveModulesWorkspace({
  env = process.env,
  startDir = HERE,
  gitCommonDir = defaultGitCommonDir,
} = {}) {
  if (env.ERPLORA_MODULES_DIR) return { dir: env.ERPLORA_MODULES_DIR, tried: [env.ERPLORA_MODULES_DIR] };
  if (env.HUB_MODULES_DIR) return { dir: env.HUB_MODULES_DIR, tried: [env.HUB_MODULES_DIR] };

  const tried = [];
  let dir = resolve(startDir);
  for (;;) {
    const candidate = join(dir, 'modules-workspace', 'modules');
    tried.push(candidate);
    if (existsSync(candidate)) return { dir: candidate, tried };
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }

  const common = gitCommonDir(startDir);
  if (common) {
    // <main checkout>/../modules-workspace/modules — the monorepo layout, seen from the hub repo.
    const candidate = resolve(dirname(common), '..', 'modules-workspace', 'modules');
    tried.push(candidate);
    if (existsSync(candidate)) return { dir: candidate, tried };
  }

  return { dir: null, tried };
}

export function syncModules({ modulesSrc, dst = PUBLIC_DST, modules = MODULES } = {}) {
  for (const id of modules) {
    const src = join(modulesSrc, id);
    const manifestPath = join(src, 'module.json');
    if (!existsSync(manifestPath)) {
      console.warn(`! module ${id}: missing module.json in ${src} (did you build it?)`);
      continue;
    }
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    const entry = manifest.ui?.entry; // e.g. dist/inventory.esm.js
    const bundlePath = join(src, entry ?? '');
    if (!entry || !existsSync(bundlePath)) {
      console.warn(`! module ${id}: missing bundle ${entry}. Run: erplora build ${id} (@erplora/module-toolkit)`);
      continue;
    }

    const dstDir = join(dst, id);
    mkdirSync(join(dstDir, dirname(entry)), { recursive: true });
    copyFileSync(manifestPath, join(dstDir, 'module.json'));
    copyFileSync(bundlePath, join(dstDir, entry));

    // Icons sidecar (ADR-0036): the module's baked SVGs, next to the bundle in dist/. The shell
    // (module-loader.loadMenu) reads it to paint the module's nav icons. Optional.
    let iconsNote = '';
    const iconsPath = join(src, dirname(entry), 'icons.json');
    if (existsSync(iconsPath)) {
      copyFileSync(iconsPath, join(dstDir, dirname(entry), 'icons.json'));
      iconsNote = ' + icons.json';
    }

    // Schema of the `settings` block (declarative settings, widget-style): the shell fetches it at
    // runtime (`/modules/<id>/<settings.schema>`) to render the generic settings form. In prod the
    // runtime serves the full module package; here the dev bridge only copies that file.
    let settingsNote = '';
    const schemaRel = manifest.settings?.schema;
    if (schemaRel) {
      const schemaSrc = join(src, schemaRel);
      if (existsSync(schemaSrc)) {
        mkdirSync(join(dstDir, dirname(schemaRel)), { recursive: true });
        copyFileSync(schemaSrc, join(dstDir, schemaRel));
        settingsNote = ` + ${schemaRel}`;
      } else {
        console.warn(`! module ${id}: settings.schema declares ${schemaRel} but it does not exist`);
      }
    }

    // Module catalogs (ADR-0055). The runtime translates the navigation, but the shell also
    // queries `/modules/<id>/locales/<lang>.json` for widget titles and other metadata.
    // Without this copy, local development silently degraded to English even though the
    // installed package did include its locales.
    let localesNote = '';
    const localesSrc = join(src, 'locales');
    if (existsSync(localesSrc)) {
      const localeFiles = readdirSync(localesSrc).filter((name) => name.endsWith('.json'));
      if (localeFiles.length) {
        mkdirSync(join(dstDir, 'locales'), { recursive: true });
        for (const name of localeFiles) {
          copyFileSync(join(localesSrc, name), join(dstDir, 'locales', name));
        }
        localesNote = ` + ${localeFiles.length} locale(s)`;
      }
    }
    console.log(`✓ sync ${id}: module.json + ${entry}${iconsNote}${settingsNote}${localesNote} → public/modules/${id}/`);
  }
}

function main() {
  const { dir, tried } = resolveModulesWorkspace();
  if (!dir || !existsSync(dir)) {
    // Tell the truth: the workspace is missing, the module builds are not the problem (hub#787).
    console.warn('! cannot find the dev modules workspace (modules-workspace/modules). Tried:');
    for (const t of tried) console.warn(`    ${t}`);
    console.warn('  The shell will boot WITHOUT modules. Point ERPLORA_MODULES_DIR (or HUB_MODULES_DIR)');
    console.warn('  at <monorepo>/modules-workspace/modules — from a worktree, the sibling of the MAIN checkout.');
    // warn + skip on purpose: predev and the Docker image build must not fail on this
    // (in the image the workspace is legitimately absent — see docker/Dockerfile).
    return;
  }
  syncModules({ modulesSrc: dir });
}

// Run only when invoked as a script (`node sync-modules.mjs`), not when imported by tests
// or by scripts/dev.mjs (which reuses resolveModulesWorkspace for HUB_MODULES_DIR).
const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href;
if (isMain) main();
