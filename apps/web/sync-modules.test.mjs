// hub#787: `pnpm dev` from a git worktree booted a hub with ZERO modules — the path to the
// sibling `modules-workspace/` repo was hardcoded relative to the checkout, and a worktree is
// not where the main checkout is. These tests pin the resolution contract:
//   1. `ERPLORA_MODULES_DIR` / `HUB_MODULES_DIR` win (same escape hatch as the pre-push hook
//      and the cargo e2e — hub#643 precedent for `blueprints/`).
//   2. Otherwise walk up from the script until a `modules-workspace/modules` dir appears
//      (covers the main checkout, unchanged behavior).
//   3. Otherwise derive the main checkout from the git common dir (covers worktrees).
//   4. When nothing is found the warning must tell the truth ("cannot find modules-workspace"),
//      not blame the module build ("¿lo compilaste?").
import { describe, it, expect } from 'vitest';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { MODULES, resolveModulesWorkspace, syncModules } from './sync-modules.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(HERE, 'sync-modules.mjs');

/** Creates <root>/modules-workspace/modules and returns both paths. */
function fakeWorkspace() {
  const root = mkdtempSync(join(tmpdir(), 'erplora-787-'));
  const modules = join(root, 'modules-workspace', 'modules');
  mkdirSync(modules, { recursive: true });
  return { root, modules };
}

describe('resolveModulesWorkspace', () => {
  it('honors ERPLORA_MODULES_DIR first, even if the dir does not exist (explicit override)', () => {
    const { dir } = resolveModulesWorkspace({
      env: { ERPLORA_MODULES_DIR: '/explicit/override', HUB_MODULES_DIR: '/other' },
      startDir: tmpdir(),
      gitCommonDir: () => null,
    });
    expect(dir).toBe('/explicit/override');
  });

  it('honors HUB_MODULES_DIR second (the var scripts/dev.mjs already documents)', () => {
    const { dir } = resolveModulesWorkspace({
      env: { HUB_MODULES_DIR: '/from/dev/mjs' },
      startDir: tmpdir(),
      gitCommonDir: () => null,
    });
    expect(dir).toBe('/from/dev/mjs');
  });

  it('walks up from startDir until it finds modules-workspace/modules (main checkout case)', () => {
    const { root, modules } = fakeWorkspace();
    try {
      const nested = join(root, 'hub', 'apps', 'web');
      mkdirSync(nested, { recursive: true });
      const { dir } = resolveModulesWorkspace({ env: {}, startDir: nested, gitCommonDir: () => null });
      expect(dir).toBe(modules);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it('derives the main checkout from the git common dir (worktree case)', () => {
    const { root, modules } = fakeWorkspace();
    try {
      // Simulate: main checkout at <root>/hub (git common dir <root>/hub/.git),
      // while startDir is a worktree far away from the monorepo.
      const commonDir = join(root, 'hub', '.git');
      mkdirSync(commonDir, { recursive: true });
      const worktree = mkdtempSync(join(tmpdir(), 'erplora-787-wt-'));
      try {
        const { dir } = resolveModulesWorkspace({
          env: {},
          startDir: worktree,
          gitCommonDir: () => commonDir,
        });
        expect(dir).toBe(modules);
      } finally {
        rmSync(worktree, { recursive: true, force: true });
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it('returns null plus the tried candidates when nothing is found', () => {
    const worktree = mkdtempSync(join(tmpdir(), 'erplora-787-none-'));
    try {
      const { dir, tried } = resolveModulesWorkspace({
        env: {},
        startDir: worktree,
        gitCommonDir: () => null,
      });
      expect(dir).toBeNull();
      expect(tried.length).toBeGreaterThan(0);
    } finally {
      rmSync(worktree, { recursive: true, force: true });
    }
  });
});

describe('syncModules', () => {
  it('copies module.json + bundle from an explicit workspace into the destination', () => {
    const src = mkdtempSync(join(tmpdir(), 'erplora-787-src-'));
    const dst = mkdtempSync(join(tmpdir(), 'erplora-787-dst-'));
    try {
      const mod = join(src, 'inventory');
      mkdirSync(join(mod, 'dist'), { recursive: true });
      writeFileSync(join(mod, 'module.json'), JSON.stringify({ ui: { entry: 'dist/inventory.esm.js' } }));
      writeFileSync(join(mod, 'dist', 'inventory.esm.js'), 'export default 1;');

      syncModules({ modulesSrc: src, dst });

      expect(existsSync(join(dst, 'inventory', 'module.json'))).toBe(true);
      expect(existsSync(join(dst, 'inventory', 'dist', 'inventory.esm.js'))).toBe(true);
    } finally {
      rmSync(src, { recursive: true, force: true });
      rmSync(dst, { recursive: true, force: true });
    }
  });
});

describe('sync-modules.mjs as a script', () => {
  it('warns truthfully (missing workspace, not "did you build it?") and exits 0 when the workspace is nowhere', () => {
    const missing = join(tmpdir(), 'erplora-787-definitely-missing');
    const res = spawnSync(process.execPath, [SCRIPT], {
      env: { ...process.env, ERPLORA_MODULES_DIR: missing, HUB_MODULES_DIR: '' },
      encoding: 'utf8',
    });
    const out = `${res.stdout}\n${res.stderr}`;
    expect(res.status).toBe(0); // predev/Docker rely on warn+skip, never a hard fail
    expect(out).toContain('modules-workspace');
    expect(out).toContain(missing);
    expect(out).not.toContain('¿lo compilaste');
  });
});

describe('the dev list of modules', () => {
  it('carries `flows`, or the automation editor cannot be opened locally AT ALL', () => {
    // The list was written for the POS batch of 24 and never grew. `flows` is the 25th module
    // (pm#110) and it is pure UI: with nothing in `public/modules/flows/` the shell's dynamic
    // `import()` fails and the screen says «no se pudo cargar el módulo» — while the RUNTIME
    // reports it installed, so the two halves of the bench disagree and the module looks broken.
    // It is not even warned about: a module missing from this list is skipped in silence.
    expect(MODULES).toContain('flows');
  });

  it('names every module exactly once', () => {
    expect(new Set(MODULES).size).toBe(MODULES.length);
  });

  it('does NOT carry `invoice_series`: the module is RETIRED and `invoice` owns numbering', () => {
    // ADR-0369 gave fiscal numbering a single owner, `invoice`, and retired `invoice_series`
    // (invoice_series#20). The marketplace already stopped offering it (saas#1538 unpublished it,
    // saas#1585 made the blueprint gate reject a retired module, pm#57 republished the 4 official
    // templates without it). This list is the LAST place in the repo that still wires the retired
    // module in BY NAME, and it is the dev bench: while it stays here, a local hub keeps showing
    // the duplicated «Tu numeración de facturas» setup step — the same title, icon and `order: 50`
    // as `invoice`'s — which is exactly the symptom the retirement exists to remove.
    //
    // Retiring closes the OFFER, not the SUPPLY: the 5 hubs that already have it installed keep
    // working, because in production the runtime serves the modules downloaded from the
    // marketplace and never reads this list (see the header of sync-modules.mjs).
    expect(MODULES).not.toContain('invoice_series');
  });

  it('does NOT carry `tickets` or `payment_gateways`: both modules were DELETED', () => {
    // Deleted on 2026-10-09 because nothing used them: neither was ever published to the
    // marketplace and no other module.json depends on them (`tickets` was a frozen helpdesk whose
    // name collided with the sales ticket; `payment_gateways` overlapped `payments`). Their repos
    // and their folders under modules-workspace go away, so a name left here would point the dev
    // bench at a module that no longer exists.
    expect(MODULES).not.toContain('tickets');
    expect(MODULES).not.toContain('payment_gateways');
  });
});
