// Regression test for ERPlora/hub#1166 — «El tema promete Inter y el hub NO la carga en ningún sitio».
//
// The theme declared `--ion-font-family: "Inter", system-ui, …` and nothing ever loaded Inter: no
// `@font-face`, no `@fontsource*` package, no `.woff2` in `public/`, no `<link>` in `index.html`.
// The fallback chain worked, so nothing broke and nothing warned — the screen simply rendered
// `system-ui` while the theme claimed a brand typeface. Measured on a real production hub
// (`qa-validate-20260822-0752.a.erplora.com`): `Array.from(document.fonts)` → `[]`, and the advance
// width of a string set in `Inter` was identical to the same string set in an invented family.
//
// ⚠️ `document.fonts.check('16px Inter')` answers `true` and LIES: it counts the fallback. Anyone
// "verifying" this in a browser with `fonts.check` closes the issue by mistake. The check that
// discriminates is static — the one in this file: read the stylesheet, list what it promises, and
// demand that every non-system family be served by something in this repo.
//
// This is a SOURCE test on purpose. A typography promise that raises no error needs something that
// looks at it for you, or the next theme edit reintroduces exactly the same silent lie (the same
// reasoning as `ionic-fill-needs-md.test.ts`, hub#760).
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('..', import.meta.url));
const APP = join(SRC, '..');

/**
 * Stylesheets that define the Hub's typography. Everything here is rendered by the shell (and
 * inherited by the printed document), so a promise made in any of them reaches the customer.
 */
const THEME_SHEETS = [
  ...readdirSync(join(SRC, 'theme'))
    .filter((name) => name.endsWith('.css'))
    .map((name) => join(SRC, 'theme', name)),
  join(SRC, 'print.css'),
];

/**
 * Families a browser resolves on its own, with no download: CSS generics, the `ui-*` keywords and
 * the fonts that ship with macOS/iOS, Windows, Android or a mainstream Linux desktop.
 *
 * Deliberately tight. Adding a merely *popular* webfont here (Inter, Open Sans, Lato…) would turn
 * this guard back into the bug it exists to prevent.
 */
const SYSTEM_FAMILIES = new Set([
  // CSS generics and global keywords
  'sans-serif', 'serif', 'monospace', 'cursive', 'fantasy', 'math', 'emoji', 'fangsong',
  'system-ui', 'ui-sans-serif', 'ui-serif', 'ui-monospace', 'ui-rounded',
  'inherit', 'initial', 'unset', 'revert', 'revert-layer',
  // Apple
  '-apple-system', 'blinkmacsystemfont', 'sf pro', 'sf mono', 'sfmono-regular', 'helvetica neue',
  'menlo', 'monaco', 'apple color emoji',
  // Windows
  'segoe ui', 'segoe ui emoji', 'segoe ui symbol', 'consolas', 'cascadia mono', 'tahoma',
  // Android
  'roboto', 'droid sans', 'droid sans mono', 'noto color emoji',
  // Linux desktops
  'cantarell', 'ubuntu', 'oxygen', 'noto sans', 'liberation sans', 'liberation mono',
  'dejavu sans', 'dejavu sans mono',
  // Web-safe core, present everywhere
  'arial', 'helvetica', 'verdana', 'trebuchet ms', 'georgia', 'times new roman', 'times',
  'courier new', 'courier',
]);

/** A `font-family` (or `--*-font-family*`) declaration and the raw value it assigns. */
const FONT_DECLARATION = /(?:^|[;{\s])(--[\w-]*font-family[\w-]*|font-family)\s*:\s*([^;}]+)/g;

/** `font-family` inside an `@font-face` block — i.e. a family the app actually SERVES. */
const FONT_FACE_BLOCK = /@font-face\s*\{([^}]*)\}/g;

/**
 * Read a stylesheet with its comments removed: a family named in prose is not a promise, and a
 * commented-out `@font-face` is not a font being served. Only `.css` is stripped — `//` inside a
 * `.ts` or `.vue` file is far more often a URL than a comment.
 */
function readSource(file: string): string {
  const source = readFileSync(file, 'utf8');
  return file.endsWith('.css') ? source.replace(/\/\*[\s\S]*?\*\//g, '') : source;
}

/**
 * Split a `font-family` value into the families it names.
 *
 * `var(--x, "Inter")` counts: the fallback is a promise too. The `var(--x)` reference itself is
 * not — it resolves to a declaration this same scan already reads.
 */
function familiesIn(value: string): string[] {
  return value
    .replace(/var\(\s*--[\w-]+/g, '')
    .replace(/[()]/g, '')
    .split(',')
    .map((part) => part.trim().replace(/^["']|["']$/g, '').trim().toLowerCase())
    .filter((part) => part.length > 0 && !part.startsWith('--'));
}

/**
 * Families a stylesheet promises that the browser will not resolve by itself and `served` does not
 * provide — i.e. the ones that silently fall through to the next entry in the chain.
 *
 * Pure on purpose: the guard below runs it over the real theme, and the positive-catch test runs it
 * over the exact string that shipped before this fix, with no dependency on the repo's state.
 */
function unservedPromises(css: string, served: Set<string>): string[] {
  const withoutFontFaces = css.replace(FONT_FACE_BLOCK, '');
  const unserved: string[] = [];
  for (const [, , value] of withoutFontFaces.matchAll(FONT_DECLARATION)) {
    for (const family of familiesIn(value)) {
      if (!SYSTEM_FAMILIES.has(family) && !served.has(family)) unserved.push(family);
    }
  }
  return unserved;
}

/** Source files that could carry an `@font-face`, anywhere in the app. */
function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === 'dist') continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(css|vue|ts|html)$/.test(entry.name)) out.push(full);
  }
  return out;
}

/** Families the app really loads: declared `@font-face`s plus any `@fontsource*` dependency. */
function servedFamilies(): Set<string> {
  const served = new Set<string>();

  for (const file of [...sourceFiles(SRC), ...sourceFiles(join(APP, 'public'))]) {
    for (const [, block] of readSource(file).matchAll(FONT_FACE_BLOCK)) {
      const declared = /font-family\s*:\s*([^;}]+)/.exec(block);
      if (declared) for (const family of familiesIn(declared[1])) served.add(family);
    }
  }

  const pkg = JSON.parse(readFileSync(join(APP, 'package.json'), 'utf8')) as {
    dependencies?: Record<string, string>;
    devDependencies?: Record<string, string>;
  };
  for (const name of Object.keys({ ...pkg.dependencies, ...pkg.devDependencies })) {
    const fontsource = /^@fontsource(?:-variable)?\/(.+)$/.exec(name);
    if (fontsource) served.add(fontsource[1].replace(/-/g, ' '));
  }

  return served;
}

describe('the theme may only promise a font the Hub actually has (hub#1166)', () => {
  it('names no font family that nothing in the Hub loads', () => {
    const served = servedFamilies();
    const offenders: string[] = [];

    for (const sheet of THEME_SHEETS) {
      for (const family of unservedPromises(readSource(sheet), served)) {
        offenders.push(`  ${relative(APP, sheet)}: "${family}"`);
      }
    }

    expect(
      offenders,
      [
        'the theme promises a font that no @font-face, @fontsource package or font file serves,',
        'so the screen silently renders the next family in the fallback chain instead:',
        ...offenders,
        'either ship the font with the app (offline: no CDN) or drop it from the declaration.',
      ].join('\n'),
    ).toEqual([]);
  });

  it('catches the positive: the pre-fix declaration is reported, naming Inter', () => {
    // The guard above passes on an empty set of offenders, which is also what a broken analyser
    // returns. So run the analyser over the exact value that shipped in `variables.css` before this
    // fix and check it flags Inter — and that the system stack that replaced it is not flagged.
    const beforeTheFix = ':root { --ion-font-family: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }';
    const afterTheFix = ':root { --ion-font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }';

    expect(unservedPromises(beforeTheFix, new Set())).toEqual(['inter']);
    expect(unservedPromises(afterTheFix, new Set())).toEqual([]);
    // And the way out stays open: promise Inter *and* serve it, and the guard is happy. Shipping a
    // brand typeface is a design decision, not something this test forbids — hiding one is.
    expect(unservedPromises(beforeTheFix, new Set(['inter']))).toEqual([]);
  });

  it('reads the declarations it is supposed to read — otherwise it guards nothing', () => {
    const declarations = THEME_SHEETS.reduce(
      (n, sheet) => n + [...readSource(sheet).matchAll(FONT_DECLARATION)].length,
      0,
    );
    expect(
      declarations,
      'no font-family declaration found in the theme: a refactor moved them and this guard went blind',
    ).toBeGreaterThan(0);

    const variables = readFileSync(join(SRC, 'theme/variables.css'), 'utf8');
    expect(
      /--ion-font-family\s*:/.test(variables),
      '--ion-font-family is the declaration this guard exists for; it must live in variables.css',
    ).toBe(true);
  });

  it('loads no font from the network: the Hub runs offline and under CSP', () => {
    const index = readFileSync(join(APP, 'index.html'), 'utf8');
    for (const [, href] of index.matchAll(/<link[^>]+href=["']([^"']+)["']/g)) {
      expect(
        /fonts\.googleapis|fonts\.gstatic|use\.typekit|\.woff2?(\?|$)/.test(href),
        `index.html must not pull a font over the network (${href}): ship it with the app instead`,
      ).toBe(false);
    }
  });
});
