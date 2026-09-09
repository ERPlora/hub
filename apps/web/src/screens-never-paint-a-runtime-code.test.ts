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

/** Every `catch (name) { … }` body in a source, paired with the name it bound. */
function catchBodies(source: string): Array<{ name: string; body: string }> {
  const found: Array<{ name: string; body: string }> = [];
  const opener = /catch\s*\(\s*([A-Za-z_$][\w$]*)\s*(?::[^)]*)?\)\s*\{/g;
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
  return found;
}

/** Why this file shows the engine's words, or an empty list when it does not. */
export function rawErrorTextReasons(source: string): string[] {
  const reasons: string[] = [];
  for (const { name, body } of catchBodies(source)) {
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
});
