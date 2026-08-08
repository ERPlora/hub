// Tests of `saveDownload` — the other door out of the till (hub#480).
//
// ADR-0255 taught the installed app to LEAVE for the system browser and left three `window.open`
// calls behind, all of them about saving a file rather than going somewhere. Sending a browser is
// no answer for those: the bytes of a `/files` download, of a backup export and of an invoice PDF
// are fetched by this page with the hub session attached, and a separate program has no session to
// fetch them with. The page has the bytes; what it lacks is somewhere to put them.
//
// In a browser that somewhere is the download manager. Inside the installed app there is none —
// wry registers no `DownloadListener` on Android at all — so «descargar» did nothing whatsoever,
// which is the same silent press ADR-0255 set out to end.
//
// Node environment: `window`/`document` are stubbed, and the installed app is simulated the way
// `lib/device.ts` detects it — by the presence of `window.__TAURI__.core.invoke`.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  SAVE_DOWNLOAD_COMMAND,
  SaveDownloadError,
  saveDownload,
  saveDownloadMessageKey,
} from './save-download';

const NAME = 'factura-2026-0042.pdf';
const BYTES = new Uint8Array([1, 2, 3, 250, 251, 252]);
/** The same six bytes as the shell will receive them. */
const BYTES_BASE64 = 'AQID+vv8';

function blob(): Blob {
  return new Blob([BYTES], { type: 'application/pdf' });
}

/** A `document` that records the anchor the browser path builds. */
function stubDocument(): { anchors: Record<string, unknown>[] } {
  const anchors: Record<string, unknown>[] = [];
  const createElement = vi.fn(() => {
    const anchor = { click: vi.fn(), remove: vi.fn() } as Record<string, unknown>;
    anchors.push(anchor);
    return anchor;
  });
  vi.stubGlobal('document', {
    createElement,
    body: { appendChild: vi.fn() },
  });
  return { anchors };
}

describe('saveDownload', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('hands the file to the browser download manager in a browser', async () => {
    const { anchors } = stubDocument();
    const createObjectURL = vi.fn(() => 'blob:the-file');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('window', { setTimeout: vi.fn() });
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });

    const saved = await saveDownload(NAME, blob());

    // `null` = the browser told the user, we have nothing to add.
    expect(saved).toBeNull();
    expect(anchors).toHaveLength(1);
    expect(anchors[0].href).toBe('blob:the-file');
    expect(anchors[0].download).toBe(NAME);
    expect(anchors[0].click).toHaveBeenCalled();
  });

  it('asks the SHELL to save it inside the installed app, and never builds an anchor', async () => {
    const { anchors } = stubDocument();
    const invoke = vi.fn().mockResolvedValue({ path: '/Users/ana/Downloads/factura-2026-0042.pdf' });
    vi.stubGlobal('window', { __TAURI__: { core: { invoke } } });

    const saved = await saveDownload(NAME, blob());

    // The literal, not the constant: asserting against `SAVE_DOWNLOAD_COMMAND` would be the same
    // name on both sides of the `=`, and a rename would pass while «descargar» went dead again.
    expect(invoke).toHaveBeenCalledWith('save_download', {
      name: NAME,
      dataBase64: BYTES_BASE64,
    });
    // An anchor here would be a second, silent copy of the same file on the platforms where the
    // webview does download — and nothing at all on the one where it does not.
    expect(anchors).toHaveLength(0);
    // The path is the point: inside the installed app there is no download shelf, so this string is
    // the only trace the user gets that the file exists.
    expect(saved).toBe('/Users/ana/Downloads/factura-2026-0042.pdf');
  });

  it('rejects when the shell could not save it, so the caller can SAY so', async () => {
    const invoke = vi.fn().mockRejectedValue('download_refused');
    vi.stubGlobal('window', { __TAURI__: { core: { invoke } } });

    await expect(saveDownload(NAME, blob())).rejects.toBeInstanceOf(SaveDownloadError);
  });

  it('rejects when the shell answers without a path — a save nobody can point at is not a save', async () => {
    const invoke = vi.fn().mockResolvedValue({});
    vi.stubGlobal('window', { __TAURI__: { core: { invoke } } });

    await expect(saveDownload(NAME, blob())).rejects.toBeInstanceOf(SaveDownloadError);
  });
});

// ── Which sentence the user reads ────────────────────────────────────────────────────────────────

describe('saveDownloadMessageKey', () => {
  it('tells a phone apart from a failure, because only one of them is actionable', () => {
    // `downloads_unreachable` is the shell saying "this device has no Downloads folder your file
    // manager can open" (Android hides `Android/data` since 11). The user can do something about
    // that — open the hub in a browser — so it gets its own sentence instead of a generic error.
    const noPlace = new SaveDownloadError(NAME, { cause: 'downloads_unreachable' });
    expect(saveDownloadMessageKey(noPlace)).toBe('download.noPlaceToSave');
  });

  it('falls back to the plain failure for everything else', () => {
    for (const cause of [
      'download_refused',
      // An app that predates hub#480: the command is simply not in its binary. It still cannot
      // save, but it stops ignoring the press.
      'Command save_download not found',
      new Error('io error: No space left on device'),
      undefined,
    ]) {
      expect(saveDownloadMessageKey(new SaveDownloadError(NAME, { cause }))).toBe('download.failed');
    }
  });

  it('treats an error from anywhere else as a plain failure too', () => {
    // The callers wrap a whole download — the authenticated fetch included — so what reaches them
    // is often not ours at all.
    expect(saveDownloadMessageKey(new Error('404'))).toBe('download.failed');
    expect(saveDownloadMessageKey('boom')).toBe('download.failed');
  });
});

// ── The command name is a contract with ANOTHER repo directory ──────────────────────────────────

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..');
const SHELL = join(SRC, '..', '..', 'tauri', 'src-tauri');

describe('the command this page invokes', () => {
  it('is one the shell actually declares', () => {
    // Rename either side alone and nothing fails to compile: Tauri's ACL simply refuses an unknown
    // command, from every remote origin, and «descargar» goes dead again — on the installed app
    // only, which is the one surface no gate opens.
    const declared = readFileSync(join(SHELL, 'build.rs'), 'utf8');
    const wired = readFileSync(join(SHELL, 'src', 'lib.rs'), 'utf8');

    expect(declared, 'build.rs no longer declares the command the page invokes').toContain(
      `"${SAVE_DOWNLOAD_COMMAND}"`,
    );
    expect(wired, 'lib.rs no longer implements the command the page invokes').toContain(
      `fn ${SAVE_DOWNLOAD_COMMAND}(`,
    );
  });
});

// ── Nobody saves a file on their own ─────────────────────────────────────────────────────────────

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

const HELPER = join('lib', 'save-download.ts');

/**
 * Every source file of the app, read ONCE.
 *
 * Both guards below sweep the whole tree, and so does `open-external.test.ts`. Reading it per test
 * is what pushes these past the 5 s default on a loaded runner — the flake would land on a guard,
 * which is the worst place for one.
 */
const SOURCES: [string, string][] = sourceFiles(SRC)
  .filter((file) => !file.endsWith(HELPER))
  .map((file) => [relative(SRC, file), readFileSync(file, 'utf8')]);

describe('every download in the app', () => {
  it('goes through the helper — a hand-rolled anchor is a no-op inside the installed app', () => {
    // The anchor dance (`URL.createObjectURL` → `a.download` → `a.click()`) is the browser API this
    // whole module exists to stop calling blind: on Android inside the app it does NOTHING, and on
    // the desktop it writes the file without telling anyone. Four screens had their own copy.
    const rolled = SOURCES.filter(([, source]) => /\.download\s*=/.test(source)).map(([at]) => at);

    expect(rolled, [
      'These files build their own download anchor instead of calling `saveDownload`. Inside the',
      'installed app that is a button that does nothing (hub#480).',
    ].join(' ')).toEqual([]);
  });

  it('handles the failure — a button that does nothing when pressed is the bug this fixes', () => {
    const unhandled: string[] = [];

    for (const [file, source] of SOURCES) {
      let at = source.indexOf('saveDownload(');
      while (at !== -1) {
        const line = source.slice(source.lastIndexOf('\n', at) + 1, source.indexOf('\n', at));
        if (!line.trimStart().startsWith('import') && !insideTry(source, at)) {
          unhandled.push(`${file}: ${line.trim()}`);
        }
        at = source.indexOf('saveDownload(', at + 1);
      }
    }

    expect(unhandled, [
      'These calls let a failed save die in silence. Wrap the call and tell the user —',
      '`saveDownloadMessageKey` picks the sentence.',
    ].join(' ')).toEqual([]);
  });

  it('has something to SAY in both languages', async () => {
    // English is the source and Spanish is what the till actually shows (ADR-0055/0199): a key that
    // only lands in `en` is a Spanish screen falling back to a dotted path.
    const [en, es] = await Promise.all([
      import('../i18n/locales/en'),
      import('../i18n/locales/es'),
    ]);

    for (const messages of [en.default, es.default]) {
      expect(messages.download.savedTo).toContain('{path}');
      expect(messages.download.noPlaceToSave).toBeTruthy();
      expect(messages.download.failed).toBeTruthy();
    }
    // Not the same sentence twice: an untranslated string is a key that was copied, not translated.
    expect(es.default.download.noPlaceToSave).not.toBe(en.default.download.noPlaceToSave);
    expect(es.default.download.failed).not.toBe(en.default.download.failed);
  });
});
