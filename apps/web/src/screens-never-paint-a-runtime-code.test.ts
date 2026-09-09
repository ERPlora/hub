// A screen never puts the engine's own error text in front of the business (hub#1693).
//
// This is the PATTERN guard, not a patch on three files. The defect it catches — «the screen paints
// whatever the runtime said» — was invisible while the runtime answered in prose: `reqwest`'s own
// Display is a sentence-shaped thing, so nobody noticed it was not OUR sentence. Since hub#1689 the
// proxies answer with a short stable code instead (`cloud_unreachable`), which is both translatable
// and unmistakably not a sentence: the business reads a lowercase English word with an underscore.
//
// Patching ImportPanel, ExportPanel and BlueprintHeroCard fixes the three screens that exist today.
// This sweep is what fixes the screen somebody writes next month: a new `.vue` that hands a caught
// error's own words to the person is named here, without anybody remembering to add it.
//
// Reading a `.message` to BRANCH on it is fine and stays out (LoginPage compares against
// `machine_registration`): the rule is about what is SHOWN, not about what is read.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('.', import.meta.url));

/**
 * Screens that still show the runtime's own words, each with the reason it is not a hub#1693 leak.
 *
 * The list may only SHRINK: a file that gets fixed must leave (the test below fails on a stale
 * entry), and a new screen is never on it. Tracked in hub#1697.
 */
const SHOWS_THE_ENGINE_TEXT_ON_PURPOSE: Record<string, string> = {
  'views/EmployeeFormPage.vue':
    'Deliberate LAST resort behind a full ladder (hub#1102/#1190/#1258): business code → rejected ' +
    'field → platform code → the sentence that came. Only reached when none of the three matched.',
  'views/ApiKeysPanel.vue':
    'Local runtime doors (/api/keys): they never proxy erplora.com, so no cloud code can reach ' +
    'this toast. Still engine prose in front of a person — hub#1697.',
  'views/SystemPage.vue':
    'Dead-letter retry/discard are local runtime doors: no cloud proxy, no cloud code. The reason ' +
    'is interpolated into a translated sentence — hub#1697.',
  'components/ModuleSettingsForm.vue':
    'The refusal arrives in the ErploraError envelope of /api/command, whose codes have been ' +
    'redacted since hub#1074; what is shown is the module refusal, not a transport code.',
  // The four below share one `reasonOf(error, fallback)` helper shape and were invisible while this
  // sweep only read `catch` bodies (rv-1698). Same class as the four above and same ticket: local
  // runtime doors, verified to emit no cloud code at all (`devices.rs`, `device_mode.rs` and
  // `hub_users.rs` never call `cloud_unreachable`), so no hub#1693 leak can reach them.
  'components/DeviceModeCard.vue':
    'Local door /api/device/mode. Shows a DeviceModeError sentence only when it carries a code — ' +
    'engine prose in front of a person, but never a cloud code — hub#1697.',
  'components/DevicesCard.vue':
    'Local door /api/devices. Shows the DevicesError sentence, falling back to its own line when ' +
    'there is none — hub#1697.',
  'views/EmployeesPage.vue':
    'Last resort behind the same ladder as EmployeeFormPage (translated code → platform code → ' +
    'the sentence that came). Local doors only — hub#1697.',
  'views/RolesPanel.vue':
    'Local door /api/hub/roles/<key>. Tries invalid-field and platform translations first and only ' +
    'then shows the RoleActivationError sentence — hub#1697.',
};

/** The idiom itself, wherever it lives — `BlueprintHeroCard` kept it in a helper, not in the catch. */
const RAW_MESSAGE_IDIOM =
  /([A-Za-z_$][\w$]*)\s+instanceof\s+Error\s*\?\s*\1\s*\.\s*message\s*:\s*String\(\s*\1\s*\)/;

/** A comparison is a read, not a paint: `e.message === 'machine_registration'` is allowed. */
const COMPARISON = /^\s*(===|!==|==|!=)/;

function vueFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) vueFiles(full, found);
    else if (entry.endsWith('.vue')) found.push(full);
  }
  return found;
}

/**
 * Where a screen gets hold of the engine's words: every body that BINDS an error to a name.
 *
 * Three bindings, not one. Scoping this to `catch` blocks alone was measured to miss four screens
 * that leak today (rv-1698) — because the house idiom for this exact concern, `reasonOf(error:
 * unknown, fallback: string)`, lives OUTSIDE the catch that calls it. `DeviceModeCard`,
 * `DevicesCard`, `EmployeesPage` and `RolesPanel` all share it and cross-reference each other in
 * their comments, so it is the shape the NEXT screen is most likely to copy.
 *
 * `unknown` is what this codebase writes when it means «this is a caught error»: that is the
 * signal, and it is why widening to the whole source is not the answer — a bare sweep for
 * `.message` also flags `metric.message` and `String(hubPinLength)`, and a guard that cries wolf
 * gets an allowlist that only grows.
 */
function errorBoundBodies(source: string): Array<{ name: string; body: string }> {
  const found: Array<{ name: string; body: string }> = [];
  const openers = [
    // `catch (e) {` and `catch (e: unknown) {`
    /catch\s*\(\s*([A-Za-z_$][\w$]*)\s*(?::[^)]*)?\)\s*\{/g,
    // `.catch((e) => {` and `.catch(e => {`. A handler that binds nothing (`.catch(() => [])`,
    // which this codebase uses everywhere to degrade) has no error to leak and never matches.
    /\.catch\s*\(\s*\(?\s*([A-Za-z_$][\w$]*)\s*(?::[^)]*)?\)?\s*=>\s*\{/g,
    // `function reasonOf(error: unknown, fallback: string): string {`
    /\(\s*([A-Za-z_$][\w$]*)\s*:\s*unknown\b[^)]*\)\s*:?[^{;]*\{/g,
  ];
  for (const opener of openers) {
    for (let m = opener.exec(source); m; m = opener.exec(source)) {
      let i = opener.lastIndex;
      let depth = 1;
      while (i < source.length && depth > 0) {
        if (source[i] === '{') depth += 1;
        else if (source[i] === '}') depth -= 1;
        i += 1;
      }
      found.push({ name: m[1], body: source.slice(opener.lastIndex, i - 1) });
    }
  }
  return found;
}

/** Why this file shows the engine's words, or an empty list when it does not. */
export function rawErrorTextReasons(source: string): string[] {
  const reasons: string[] = [];
  for (const { name, body } of errorBoundBodies(source)) {
    const id = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const shapes: Array<[RegExp, string]> = [
      [new RegExp(`\\b${id}\\s*\\.\\s*message\\b`, 'g'), `${name}.message`],
      [new RegExp(`String\\(\\s*${id}\\s*\\)`, 'g'), `String(${name})`],
      [new RegExp(`\\(\\s*${id}\\s+as\\s+Error\\s*\\)\\s*\\.\\s*message\\b`, 'g'), `(${name} as Error).message`],
    ];
    for (const [shape, label] of shapes) {
      for (let m = shape.exec(body); m; m = shape.exec(body)) {
        if (COMPARISON.test(body.slice(m.index + m[0].length))) continue;
        reasons.push(label);
      }
    }
  }
  if (RAW_MESSAGE_IDIOM.test(source)) reasons.push('err instanceof Error ? err.message : String(err)');
  return [...new Set(reasons)];
}

const offenders = new Map<string, string[]>();
for (const file of vueFiles(SRC)) {
  const reasons = rawErrorTextReasons(readFileSync(file, 'utf8'));
  if (reasons.length) offenders.set(file.slice(SRC.length).replace(/\\/g, '/'), reasons);
}

describe('no screen shows the runtime its own error text (hub#1693)', () => {
  it('finds the screens it is supposed to find', () => {
    // The floor that makes the sweep honest: a lexer that silently stopped matching would report
    // zero offenders and pass. There are `.vue` files, and the known ones are among the results.
    expect(vueFiles(SRC).length).toBeGreaterThan(20);
    expect([...offenders.keys()].sort()).toEqual(Object.keys(SHOWS_THE_ENGINE_TEXT_ON_PURPOSE).sort());
  });

  it('names any screen that is not on the list', () => {
    const leaking = [...offenders.entries()].filter(([f]) => !(f in SHOWS_THE_ENGINE_TEXT_ON_PURPOSE));
    expect(
      leaking.map(([f, why]) => `${f} → ${why.join(', ')}`),
      'These screens hand the engine\'s own words to the business. Translate the stable code with ' +
        '`runtimeErrorSentence` (see ImportPanel), or add the file to ' +
        'SHOWS_THE_ENGINE_TEXT_ON_PURPOSE with the reason it is not a leak.',
    ).toEqual([]);
  });

  it('has no stale entry: a screen that got fixed leaves the list', () => {
    const fixed = Object.keys(SHOWS_THE_ENGINE_TEXT_ON_PURPOSE).filter((f) => !offenders.has(f));
    expect(fixed, 'These no longer show the engine text: remove them from the list.').toEqual([]);
  });

  it('reads a paint and ignores a comparison', () => {
    // The control has to catch the positive, and only the positive. Both halves are checked here
    // so a lexer that matched nothing (or everything) cannot pass the sweep above by luck.
    expect(rawErrorTextReasons('try { a(); } catch (e) { msg.value = e.message; }')).toEqual(['e.message']);
    expect(rawErrorTextReasons("try { a(); } catch (e) { if (e.message === 'x') retry(); }")).toEqual([]);
    expect(rawErrorTextReasons('const m = (e: unknown) => (e instanceof Error ? e.message : String(e));')).toEqual([
      'err instanceof Error ? err.message : String(err)',
    ]);
    expect(rawErrorTextReasons('try { a(); } catch (e) { msg.value = t("x"); }')).toEqual([]);
  });

  it('sees the paint wherever the error is BOUND, not only inside a catch (rv-1698)', () => {
    // A `catch` block is not the only place a screen gets hold of the engine's words, and the two
    // other places are not hypothetical: `reasonOf(error: unknown, fallback: string)` is this
    // repo's house idiom for exactly this concern (four screens share it, cross-referencing each
    // other in comments), and it lives OUTSIDE the catch that calls it. A sweep scoped to catch
    // bodies reads the fixed files and reports zero — the shape it was written from.
    expect(
      rawErrorTextReasons(
        'function reasonOf(error: unknown, fallback: string): string {\n' +
          '  return error instanceof DevicesError && error.message ? error.message : fallback;\n' +
          '}',
      ),
    ).toEqual(['error.message']);
    expect(rawErrorTextReasons('void load().catch((e) => { msg.value = e.message; });')).toEqual(['e.message']);
    expect(rawErrorTextReasons('void load().catch(e => { msg.value = String(e); });')).toEqual(['String(e)']);

    // And the same two bindings still tell a read from a paint: comparing is allowed anywhere.
    expect(
      rawErrorTextReasons("function isGone(error: unknown): boolean {\n  return error.message === 'gone';\n}"),
    ).toEqual([]);
    // A handler that takes no error cannot leak one: `.catch(() => …)` is all over this codebase.
    expect(rawErrorTextReasons('void load().catch(() => []);')).toEqual([]);
  });
});
