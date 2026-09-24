import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveSettingsTab } from './settings-tabs';

// hub#2016 — the bell's «printing stopped» alert pushed `/settings#receipts`. There is no such tab,
// and `resolveSettingsTab` degrades whatever it does not know to General IN SILENCE, so the owner
// landed next to the country and the currency instead of the print coverage in «Tickets». Same
// shape as hub#1954 (the business-identity «Configure» link) and verifactu#49 before it: nothing
// fails, the link just goes to the wrong place. This guard reads every deep link into Ajustes the
// hub ships (shell AND runtime — the setup checklist routes are built in Rust) and requires each
// one to name a tab that exists, or a retired alias the resolver still maps (`#tax`).

const HUB_ROOT = fileURLToPath(new URL('../../../../', import.meta.url));
const SCANNED_ROOTS = ['apps/web/src', 'apps/web/tests', 'crates'];
const SKIPPED_DIRS = new Set(['node_modules', 'target', 'dist']);
const SCANNED_EXTENSIONS = /\.(vue|ts|rs)$/;

/** The three ways the hub writes a link into Ajustes: `/settings#x`, `/settings?tab=x` (the legacy
 *  query the auth gate rewrites to the hash) and a router object `{ path: '/settings', hash: '#x' }`. */
const LINK_PATTERNS = [
  /\/settings#([A-Za-z_-]+)/g,
  /\/settings\?tab=([A-Za-z_-]+)/g,
  /path:\s*['"]\/settings['"]\s*,\s*(?:query:\s*\{[^}]*\}\s*,\s*)?hash:\s*['"]#([A-Za-z_-]+)['"]/g,
];

function settingsTabLinks(source: string): string[] {
  return LINK_PATTERNS.flatMap((pattern) => [...source.matchAll(pattern)].map((m) => m[1]));
}

/** A tab name is live when the resolver lands on it (or on its alias) rather than on the fallback. */
function isKnownTab(name: string): boolean {
  return name === 'hub' || resolveSettingsTab(`#${name}`) !== 'hub';
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    if (SKIPPED_DIRS.has(entry)) return [];
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    // Unit tests mock routes with whatever hash they need; the contract is what ships.
    return SCANNED_EXTENSIONS.test(entry) && !entry.endsWith('.test.ts') ? [path] : [];
  });
}

const shippedLinks = SCANNED_ROOTS.flatMap((root) => sourceFiles(join(HUB_ROOT, root))).flatMap((file) =>
  settingsTabLinks(readFileSync(file, 'utf8')).map((tab) => ({ file: relative(HUB_ROOT, file), tab })),
);

describe('deep links into Ajustes name a tab that exists (hub#2016)', () => {
  it('the extractor sees each of the three link shapes', () => {
    expect(settingsTabLinks("router.push('/settings#permissions')")).toEqual(['permissions']);
    expect(settingsTabLinks('pub const R: &str = "/settings?tab=data";')).toEqual(['data']);
    expect(settingsTabLinks("router.push({ path: '/settings', hash: '#receipts' })")).toEqual(['receipts']);
    expect(settingsTabLinks("{ path: '/settings', query: { a: '1' }, hash: '#tickets' }")).toEqual(['tickets']);
  });

  it('an unknown tab is caught, a retired alias is not', () => {
    expect(isKnownTab('receipts')).toBe(false);
    expect(isKnownTab('tickets')).toBe(true);
    expect(isKnownTab('tax')).toBe(true);
  });

  it('actually scans the shell and the runtime (not vacuously green)', () => {
    const files = new Set(shippedLinks.map((l) => l.file));
    expect(files).toContain('apps/web/src/views/AppsPage.vue');
    expect(files).toContain('crates/runtime/src/setup_status.rs');
  });

  it('every shipped link lands on a real tab instead of degrading to General', () => {
    const broken = shippedLinks.filter((l) => !isKnownTab(l.tab)).map((l) => `${l.file} → #${l.tab}`);
    expect(broken).toEqual([]);
  });
});
