// hub#760 — «Datos del negocio: los campos fiscales son invisibles».
//
// `fill="outline"` on an Ionic form control is only honoured in `md` mode. From Ionic 8.8's own
// source (`@ionic/core/dist/collection/components/input/input.js`):
//
//     const hasOutlineFill = mode === 'md' && this.fill === 'outline';
//
// The Hub pins `mode: 'ios'` (ADR-0143, `src/main.ts`), so the attribute is a silent no-op: the
// control renders with no box, no border and no surface — just a label floating on the page
// background. Nothing throws, nothing warns; the form simply looks like static text, which is
// exactly what QA reported on Settings → Business (NIF / legal name / fiscal address).
//
// These are SOURCE tests on purpose. A styling bug that raises no error needs something that
// looks at it for you, otherwise it creeps back into the next screen. Same guard the Cloud
// Portal already carries (`saas/tests/unit/test_ionic_fill_needs_md.py`, saas#1080) — parity
// Cloud↔Hub.
import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('..', import.meta.url));

/** Opening tag of a form control, even when its attributes span several lines. */
const CONTROL = /<ion-(?:input|select|textarea)(?=[\s/>])[^>]*>/gs;

function vueFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...vueFiles(full));
    else if (entry.name.endsWith('.vue')) out.push(full);
  }
  return out;
}

function controlsWithDeadFill(source: string): string[] {
  const dead: string[] = [];
  for (const tag of source.match(CONTROL) ?? []) {
    if (!/\bfill=/.test(tag)) continue;
    if (/\bmode="md"/.test(tag)) continue;
    dead.push(tag.replace(/\s+/g, ' ').slice(0, 110));
  }
  return dead;
}

describe('a control that declares `fill` must declare mode="md" (hub#760)', () => {
  it('the Hub really does pin Ionic to `ios` mode — the premise of this guard', () => {
    const main = readFileSync(join(SRC, 'main.ts'), 'utf8');
    expect(
      /use\(IonicVue,\s*\{[^}]*mode:\s*'ios'/.test(main),
      'if the Hub ever switches to `md` globally this whole guard is dead weight — delete it',
    ).toBe(true);
  });

  it('the shell hooks element registration BEFORE @ionic/vue registers anything (hub#1060)', () => {
    // The per-control rule above only reaches source we own. Everything a merchant types into is a
    // module Web Component from another repo, so the shell also normalizes `fill` → `mode="md"` at
    // `customElements.define` time (`src/lib/ionic-fill.ts`). That hook only exists if its import
    // comes first: `@ionic/vue` registers `ion-input` & co. on import, and the HTML spec captures a
    // custom element's lifecycle callbacks inside `define`. Move the import down and the fix
    // vanishes with no error at all — which is the exact failure mode this whole file is about.
    const main = readFileSync(join(SRC, 'main.ts'), 'utf8');
    const boot = main.indexOf("import './lib/ionic-fill.boot'");
    const ionic = main.indexOf("from '@ionic/vue'");
    expect(boot, 'main.ts must import ./lib/ionic-fill.boot').toBeGreaterThanOrEqual(0);
    expect(ionic, 'main.ts is supposed to import @ionic/vue').toBeGreaterThanOrEqual(0);
    expect(
      boot < ionic,
      'the fill hook must be imported before @ionic/vue, or it silently stops working',
    ).toBe(true);
  });

  it('Ionic ships outline styling only for `md`, not for `ios`', () => {
    // Pinned to the dependency itself, not to a snapshot of it: if a future Ionic starts styling
    // `fill` in `ios`, this test tells us the guard can go instead of quietly outliving its cause.
    const require = createRequire(import.meta.url);
    const core = dirname(require.resolve('@ionic/core/package.json'));
    const styles = join(core, 'dist/collection/components/input');
    const ios = readFileSync(join(styles, 'input.ios.css'), 'utf8');
    const md = readFileSync(join(styles, 'input.md.css'), 'utf8');

    expect(md, '`md` is supposed to be the mode that paints the outline').toContain('input-fill-outline');
    expect(ios, '`ios` has no outline styling: `fill` there is a no-op').not.toContain('input-fill-outline');
  });

  it('no ion-input / ion-select / ion-textarea declares a `fill` that will never paint', () => {
    const offenders: string[] = [];
    for (const file of vueFiles(SRC)) {
      for (const tag of controlsWithDeadFill(readFileSync(file, 'utf8'))) {
        offenders.push(`  ${relative(SRC, file)}: ${tag}`);
      }
    }
    expect(
      offenders,
      ['these controls will render with no box at all — add mode="md" to each:', ...offenders].join('\n'),
    ).toEqual([]);
  });

  it('the scan actually reaches the views — otherwise it would pass on an empty set', () => {
    const total = vueFiles(SRC).reduce(
      (n, file) => n + (readFileSync(file, 'utf8').match(CONTROL) ?? []).length,
      0,
    );
    expect(total, 'no form controls found: a refactor moved them and this guard stopped guarding').toBeGreaterThan(30);
  });
});
