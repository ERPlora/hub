// Tests of `openExternal` — the ONE door out of the till (hub#475).
//
// The helper used to be a single `window.open(_blank)` line, written when the Hub really was a
// pure PWA. Since ADR-0196/0180 the same web app also runs inside the webview of the installed
// app, and there `window.open` opens NOTHING: the page is handed no `shell`/`opener` plugin and
// the webview spawns no window. So the buttons that CHARGE — the module checkout of ADR-0114, the
// plans page, the billing portal — did nothing at all when pressed. No window, no error, no log.
//
// Node environment: `window` is stubbed, and the installed app is simulated the same way
// `lib/device.ts` detects it — by the presence of `window.__TAURI__.core.invoke`.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { OPEN_EXTERNAL_COMMAND, openExternal } from './open-external';

const CHECKOUT = 'https://erplora.com/dashboard/billing/modules/pos/?hub=h1&utm_source=hub';

describe('openExternal', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens a new tab with noopener in the browser', async () => {
    const open = vi.fn();
    vi.stubGlobal('window', { open });

    await openExternal(CHECKOUT);

    expect(open).toHaveBeenCalledWith(CHECKOUT, '_blank', 'noopener');
  });

  it('asks the shell for the SYSTEM browser inside the installed app, never window.open', async () => {
    const open = vi.fn();
    const invoke = vi.fn().mockResolvedValue(null);
    vi.stubGlobal('window', { open, __TAURI__: { core: { invoke } } });

    await openExternal(CHECKOUT);

    // The literal, not the constant: asserting against `OPEN_EXTERNAL_COMMAND` would be the same
    // name on both sides of the `=`, and a rename would pass while the till stopped buying.
    expect(invoke).toHaveBeenCalledWith('open_external_url', { url: CHECKOUT });
    expect(open).not.toHaveBeenCalled();
  });

  it('rejects when the shell could not open it, so the caller can SAY so', async () => {
    const open = vi.fn();
    const invoke = vi.fn().mockRejectedValue('external_url_refused');
    vi.stubGlobal('window', { open, __TAURI__: { core: { invoke } } });

    await expect(openExternal(CHECKOUT)).rejects.toThrow(/open_external_failed/);
    // No silent second chance: navigating the webview itself would put a checkout INSIDE the
    // installed app, which is exactly what ADR-0114 §4 took out of it for Google Play.
    expect(open).not.toHaveBeenCalled();
  });
});

// ── The command name is a contract with ANOTHER repo directory ──────────────────────────────────

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..');
const SHELL = join(SRC, '..', '..', 'tauri', 'src-tauri');

describe('the command this page invokes', () => {
  it('is one the shell actually declares', () => {
    // ADR-0247 pinned four artifacts that describe the same command list; this page is the fifth,
    // and the only one written in another language, in another directory, by another test suite.
    // Rename either side alone and nothing fails to compile: Tauri's ACL simply refuses an unknown
    // command, from every remote origin, and the buy button goes dead again — on the installed app
    // only, which is the one surface no gate opens.
    const declared = readFileSync(join(SHELL, 'build.rs'), 'utf8');
    const wired = readFileSync(join(SHELL, 'src', 'lib.rs'), 'utf8');

    expect(declared, 'build.rs no longer declares the command the page invokes').toContain(
      `"${OPEN_EXTERNAL_COMMAND}"`,
    );
    expect(wired, 'lib.rs no longer implements the command the page invokes').toContain(
      `fn ${OPEN_EXTERNAL_COMMAND}(`,
    );
  });
});

// ── Nobody may swallow that rejection ────────────────────────────────────────────────────────────

function sourceFiles(dir: string, into: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) sourceFiles(path, into);
    else if (/\.(ts|vue)$/.test(entry.name) && !entry.name.endsWith('.test.ts')) into.push(path);
  }
  return into;
}

/**
 * Is the call at `at` lexically inside a `try { … } catch`?
 *
 * Every `try` in this code base has its `catch`, so counting openers against closers before the
 * call answers it without parsing: more `try {` than `} catch` means one is still open.
 */
function insideTry(source: string, at: number): boolean {
  const before = source.slice(0, at);
  const opened = before.match(/\btry\s*\{/g)?.length ?? 0;
  const closed = before.match(/\}\s*catch\b/g)?.length ?? 0;
  return opened > closed;
}

describe('every caller of openExternal', () => {
  it('handles the failure — a button that does nothing when pressed is the bug this fixes', () => {
    const unhandled: string[] = [];

    for (const file of sourceFiles(SRC)) {
      if (file.endsWith(join('lib', 'open-external.ts'))) continue;
      const source = readFileSync(file, 'utf8');
      let at = source.indexOf('openExternal(');
      while (at !== -1) {
        // The import statement names it too, and that is not a call.
        const line = source.slice(source.lastIndexOf('\n', at) + 1, source.indexOf('\n', at));
        if (!line.trimStart().startsWith('import') && !insideTry(source, at)) {
          unhandled.push(`${relative(SRC, file)}: ${line.trim()}`);
        }
        at = source.indexOf('openExternal(', at + 1);
      }
    }

    expect(unhandled, [
      'These calls let a failed trip to the browser die in silence, which is the whole defect of',
      'hub#475: inside the installed app the user presses BUY and nothing happens. Wrap the call',
      'and tell them.',
    ].join(' ')).toEqual([]);
  });

  it('has something to SAY in both languages', async () => {
    // Telling the user is the point, so the sentence has to exist where the user reads it. English
    // is the source and Spanish is what the till actually shows (ADR-0055/0199): a key that only
    // lands in `en` is a Spanish screen falling back to a dotted path.
    const [en, es] = await Promise.all([
      import('../i18n/locales/en'),
      import('../i18n/locales/es'),
    ]);

    // `planLimits.upgradeError` used to be checked here. Its caller is gone (hub#479): the button
    // that opened the SaaS plans page was a route from the app to a payment, which both stores
    // reject. `appUpdate.failed` takes its place and is the better witness anyway — it belongs to
    // the update channel (hub#400), the one trip out that MUST keep working after the sweep.
    for (const messages of [en.default, es.default]) {
      expect(messages.appUpdate.failed).toBeTruthy();
      expect(messages.profile.cloudAccountError).toBeTruthy();
    }
    // Not the same sentence twice: an untranslated string is a key that was copied, not translated.
    expect(es.default.appUpdate.failed).not.toBe(en.default.appUpdate.failed);
    expect(es.default.profile.cloudAccountError).not.toBe(en.default.profile.cloudAccountError);
  });
});
