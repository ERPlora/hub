// hub#1588 — the build must SAY which OutfitKit it put in the image.
//
// Until now the only way to know was the image's build DATE, cross-referenced by hand against
// npm's publish dates (`module-toolkit/src/validate-outfitkit-floor.mjs` keeps that derived table).
// These tests pin the contract that replaces it: every production build emits
// `dist/outfitkit-version.json` with the version it ACTUALLY installed, and a build that cannot
// say it fails instead of shipping a lie.
//
// Each test is written so the failure mode it guards is RED, not just so the happy path is green:
// reading the declared range instead of the installed package, resolving the wrong tree, dropping
// the plugin from the config and emitting an empty stamp all fail here.
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  OUTFITKIT_VERSION_FILE,
  resolveOutfitkitVersion,
  outfitkitVersionStamp,
} from './outfitkit-version.ts';

const HERE = dirname(fileURLToPath(import.meta.url));

let fixture: string;

/** Writes a `node_modules/@erplora/outfitkit/package.json` with `version` under `root`. */
function installOutfitkit(root: string, version: string): void {
  const dir = join(root, 'node_modules', '@erplora', 'outfitkit');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'package.json'), JSON.stringify({ name: '@erplora/outfitkit', version }));
}

/** The app dir inside the fixture, mirroring the real `<repo>/apps/web` depth. */
function appDir(root: string): string {
  const dir = join(root, 'apps', 'web');
  mkdirSync(dir, { recursive: true });
  return dir;
}

/**
 * Minimal Rollup plugin context: captures `emitFile` and turns `this.error` into a throw, which is
 * what Rollup itself does (the build aborts).
 */
function fakeContext() {
  const emitted: { type: string; fileName: string; source: string }[] = [];
  return {
    emitted,
    ctx: {
      emitFile(file: { type: string; fileName: string; source: string }) {
        emitted.push(file);
      },
      error(err: { code?: string; message?: string }): never {
        throw Object.assign(new Error(err.message ?? 'plugin error'), { code: err.code });
      },
    },
  };
}

/** Runs the plugin's `generateBundle` hook against a fake context. */
async function runStamp(plugin: unknown, ctx: unknown) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const hook = (plugin as any).generateBundle;
  return hook.call(ctx, {}, {});
}

beforeEach(() => {
  fixture = mkdtempSync(join(tmpdir(), 'erplora-outfitkit-'));
});

afterEach(() => {
  rmSync(fixture, { recursive: true, force: true });
});

describe('resolveOutfitkitVersion (hub#1588)', () => {
  it('reports the INSTALLED version, not the range declared in package.json', () => {
    const app = appDir(fixture);
    // The declared range is what lies today: the Dockerfile re-resolves `@latest` over it.
    writeFileSync(
      join(app, 'package.json'),
      JSON.stringify({ dependencies: { '@erplora/outfitkit': '^0.1.52' } }),
    );
    installOutfitkit(app, '0.1.65');

    expect(resolveOutfitkitVersion(app)).toBe('0.1.65');
  });

  it('prefers the app tree over the workspace root when both carry a copy', () => {
    const app = appDir(fixture);
    installOutfitkit(app, '0.1.65'); // what apps/web actually resolves
    installOutfitkit(fixture, '0.1.50'); // a stale hoisted copy at the workspace root

    expect(resolveOutfitkitVersion(app)).toBe('0.1.65');
  });

  it('falls back to the workspace root when the app tree has no copy (pnpm hoisting)', () => {
    const app = appDir(fixture);
    installOutfitkit(fixture, '0.1.61');

    expect(resolveOutfitkitVersion(app)).toBe('0.1.61');
  });

  it('is empty when nothing is installed', () => {
    expect(resolveOutfitkitVersion(appDir(fixture))).toBe('');
  });

  it('is empty when the installed package.json is unreadable', () => {
    const app = appDir(fixture);
    const dir = join(app, 'node_modules', '@erplora', 'outfitkit');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'package.json'), '{ not json');

    expect(resolveOutfitkitVersion(app)).toBe('');
  });

  it('resolves the version really installed for apps/web in THIS checkout', () => {
    const installed = JSON.parse(
      readFileSync(join(HERE, 'node_modules', '@erplora', 'outfitkit', 'package.json'), 'utf8'),
    ).version;

    expect(resolveOutfitkitVersion(HERE)).toBe(installed);
  });
});

describe('outfitkitVersionStamp (hub#1588)', () => {
  it('emits the stamp as a build asset with both versions', async () => {
    const { ctx, emitted } = fakeContext();

    await runStamp(outfitkitVersionStamp({ outfitkit: '0.1.65', hub: '1.1.14' }), ctx);

    expect(emitted).toHaveLength(1);
    expect(emitted[0].type).toBe('asset');
    expect(emitted[0].fileName).toBe(OUTFITKIT_VERSION_FILE);
    expect(JSON.parse(emitted[0].source)).toEqual({ outfitkit: '0.1.65', hub: '1.1.14' });
  });

  it('aborts the build when the version could not be resolved, instead of stamping a blank', async () => {
    const { ctx, emitted } = fakeContext();

    await expect(runStamp(outfitkitVersionStamp({ outfitkit: '', hub: '1.1.14' }), ctx)).rejects.toMatchObject({
      code: 'OUTFITKIT_VERSION_UNRESOLVED',
    });
    expect(emitted).toHaveLength(0);
  });

  it('only runs on build: `vite dev` has no dist to stamp', () => {
    expect(outfitkitVersionStamp({ outfitkit: '0.1.65', hub: '1.1.14' }).apply).toBe('build');
  });
});

describe('vite.config emits the stamp (hub#1588)', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function flatten(plugins: any): any[] {
    return Array.isArray(plugins) ? plugins.flatMap(flatten) : [plugins];
  }

  async function loadConfig() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (await import('./vite.config.ts')).default as any;
  }

  it('the plugin is WIRED — without it a build ships no stamp at all', async () => {
    const cfg = await loadConfig();
    const stamp = flatten(cfg.plugins).find((p) => p?.name === 'erplora-outfitkit-version');

    expect(stamp).toBeDefined();
  });

  it('stamps the SAME version the shell reports at runtime (__OUTFITKIT_VERSION__)', async () => {
    const cfg = await loadConfig();
    const stamp = flatten(cfg.plugins).find((p) => p?.name === 'erplora-outfitkit-version');
    const { ctx, emitted } = fakeContext();

    await runStamp(stamp, ctx);

    expect(JSON.parse(emitted[0].source).outfitkit).toBe(JSON.parse(cfg.define.__OUTFITKIT_VERSION__));
  });

  it('stamps the version installed in node_modules, not the range in package.json', async () => {
    const installed = JSON.parse(
      readFileSync(join(HERE, 'node_modules', '@erplora', 'outfitkit', 'package.json'), 'utf8'),
    ).version;
    const declared = JSON.parse(readFileSync(join(HERE, 'package.json'), 'utf8')).dependencies[
      '@erplora/outfitkit'
    ];
    const cfg = await loadConfig();
    const stamp = flatten(cfg.plugins).find((p) => p?.name === 'erplora-outfitkit-version');
    const { ctx, emitted } = fakeContext();

    await runStamp(stamp, ctx);

    const stamped = JSON.parse(emitted[0].source).outfitkit;
    expect(stamped).toBe(installed);
    expect(declared).not.toBe(stamped); // the range is a range, and it is not what shipped
  });
});
