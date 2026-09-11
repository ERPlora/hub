import { readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const viewSource = (name: string): string =>
  readFileSync(new URL(`./${name}`, import.meta.url), 'utf8');

const appPageSource = (): string =>
  readFileSync(new URL('../components/AppPage.vue', import.meta.url), 'utf8');

const polishSource = (): string =>
  readFileSync(new URL('../theme/polish.css', import.meta.url), 'utf8');

const themeVariablesSource = (): string =>
  readFileSync(new URL('../theme/variables.css', import.meta.url), 'utf8');

/** CSS comments carry example declarations; they are not rules. */
const stripCssComments = (css: string): string => css.replace(/\/\*[\s\S]*?\*\//g, '');

type SurfaceDir = 'views' | 'components';

const listVue = (dir: SurfaceDir): string[] =>
  readdirSync(new URL(`../${dir}/`, import.meta.url))
    .filter((name) => name.endsWith('.vue'))
    .sort();

const surfaceSource = (dir: SurfaceDir, name: string): string =>
  readFileSync(new URL(`../${dir}/${name}`, import.meta.url), 'utf8');

/**
 * Innermost `{ … }` blocks of every `<style>` in a single-file component. Nested at-rules
 * (`@media`, `@container`) are transparent: their inner rules are the innermost blocks.
 */
function styleRules(source: string): Array<{ selector: string; body: string }> {
  const rules: Array<{ selector: string; body: string }> = [];
  for (const style of source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)) {
    for (const block of stripCssComments(style[1]).matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
      const selector = block[1].trim().split('\n').pop()?.trim() ?? '';
      rules.push({ selector, body: block[2] });
    }
  }
  return rules;
}

/**
 * hub#1605 — a shell surface never caps its own width. The shell dropped its `72rem` cap on
 * 2026-08-15 (`.hub-detail-shell`, guarded below); the panels that still carried one predate
 * that decision and re-created the narrow, centred island inside a fluid page.
 *
 * A "container cap" is a fixed `max-width` of container size (≥ 480px / 30rem) — small caps are
 * intrinsic control sizes (a chip, a select, a skeleton bar) — or ANY fixed `max-width` paired
 * with an `auto` horizontal margin, which is the centred island itself, whatever its size.
 */
const CONTAINER_CAP_PX = 480;
const FIXED_MAX_WIDTH = /(?<![-\w])max-width:\s*([^;]+)/;
const FIXED_LENGTH = /([\d.]+)(px|rem|em|ch)\b/g;
const AUTO_INLINE_MARGIN = /(?<![-\w])margin(-inline)?:[^;]*\bauto\b/;

function widthCapOffenders(source: string): string[] {
  const offenders: string[] = [];
  for (const { selector, body } of styleRules(source)) {
    const cap = body.match(FIXED_MAX_WIDTH);
    if (!cap) continue;
    const px = [...cap[1].matchAll(FIXED_LENGTH)].map(([, n, unit]) =>
      unit === 'px' ? Number(n) : Number(n) * 16,
    );
    if (px.length === 0) continue;
    const centred = AUTO_INLINE_MARGIN.test(body);
    if (Math.max(...px) >= CONTAINER_CAP_PX || centred) {
      offenders.push(`${selector} → max-width: ${cap[1].trim()}${centred ? ' + margin auto' : ''}`);
    }
  }
  return offenders;
}

/**
 * Not shell panels: a Word document painted as a sheet of paper inside the file preview modal.
 * Paper has a page width by definition; stretching it to the viewport is what would be wrong.
 */
const PAPER_DOCUMENTS: Record<string, string[]> = {
  'components/FilePreviewModal.vue': ['.preview-document'],
};

describe('shared Hub page alignment', () => {
  it('keeps data-heavy destinations fluid', () => {
    for (const page of [
      'DashboardPage.vue',
      'EmployeesPage.vue',
      'FilesPage.vue',
      'BillingPage.vue',
      'AppsPage.vue',
      'ModuleView.vue',
    ]) {
      const source = viewSource(page);
      expect(source).toContain('<AppPage');
      expect(source).not.toContain('content-layout="detail');
    }
  });

  it('centers every readable core destination on the same detail shell', () => {
    for (const page of [
      'EmployeeFormPage.vue',
      'ProfilePage.vue',
      'SettingsPage.vue',
      'SystemPage.vue',
    ]) {
      expect(viewSource(page)).toContain('content-layout="detail"');
    }
    expect(viewSource('ApiDocsPage.vue')).toContain('content-layout="detail-fill"');
  });

  it('owns the detail wrapper in AppPage and preserves a full-height variant', () => {
    const source = appPageSource();
    expect(source).toContain("contentLayout !== 'fluid'");
    expect(source).toContain("contentLayout: 'fluid'");
    expect(source).toContain('class="hub-detail-shell"');
    expect(source).toContain("'hub-detail-shell--fill': contentLayout === 'detail-fill'");
    expect(source).toContain('<slot v-else />');
  });

  it('leaves readable destinations unconstrained inside the shared page gutter', () => {
    const source = polishSource();
    const detailRule = source.match(/\.hub-detail-shell\s*\{([\s\S]*?)\}/)?.[1] ?? '';
    expect(detailRule).toMatch(/min-width:\s*0/);
    expect(detailRule).not.toMatch(/^\s*width\s*:/m);
    expect(detailRule).not.toMatch(/^\s*max-width\s*:/m);
    expect(detailRule).not.toContain('72rem');
    expect(detailRule).not.toMatch(/margin-inline:\s*auto/);
    expect(source).toMatch(/\.hub-detail-shell--fill\s*\{[\s\S]*?height:\s*100%/);
  });

  it('hub#1605: the width-cap detector catches the centred island and the container cap', () => {
    // Positive control: the exact shapes that regressed, plus the shell's old `min(100%, 72rem)`.
    expect(
      widthCapOffenders(
        '<style scoped>.a { max-width: 960px; margin: 0 auto; }</style>' +
          '<style>@media (min-width: 768px) { .b { max-width: 36rem; } }' +
          '.c { width: min(100%, 72rem); max-width: min(100%, 72rem); }' +
          '.d { max-width: 20rem; margin-inline: auto; }</style>',
      ),
    ).toEqual([
      '.a → max-width: 960px + margin auto',
      '.b → max-width: 36rem',
      '.c → max-width: min(100%, 72rem)',
      '.d → max-width: 20rem + margin auto',
    ]);
    // Intrinsic sizes and modal tokens are not caps.
    expect(
      widthCapOffenders(
        '<style>.chip { max-width: 12rem; } .range { max-width: 240px; margin: 0 4px 8px; }' +
          '.full { max-width: 100%; } ion-modal { --max-width: 1400px; }</style>',
      ),
    ).toEqual([]);
  });

  it('hub#1605: no shell surface caps or centres its own width', () => {
    const surfaces: Array<[SurfaceDir, string]> = [
      ...listVue('views')
        .filter((name) => surfaceSource('views', name).includes('<AppPage'))
        .map((name): [SurfaceDir, string] => ['views', name]),
      ...listVue('components').map((name): [SurfaceDir, string] => ['components', name]),
    ];
    expect(surfaces.length).toBeGreaterThan(10);

    const offenders: string[] = [];
    for (const [dir, name] of surfaces) {
      const paper = PAPER_DOCUMENTS[`${dir}/${name}`] ?? [];
      for (const offender of widthCapOffenders(surfaceSource(dir, name))) {
        if (paper.some((selector) => offender.startsWith(`${selector} →`))) continue;
        offenders.push(`${dir}/${name}: ${offender}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

/**
 * hub#1730 · hub#1745 — a shell WORK SURFACE is never shorter than a usable working surface.
 *
 * A "work surface" is the element a screen hands to the shell's scroller: `.outlet` in
 * `ModuleView.vue`, `.fill` in the core screens, `.api-docs-wrap`, `.hub-detail-shell--fill`.
 * They all pin themselves to `height: 100%` so that `ok-data-table[fill]` has a DEFINED height to
 * constrain against (see the comment on `.outlet` itself). The side effect nobody costed: an
 * element that is exactly `100%` of its scroll container can never OVERFLOW it, so `ion-content`
 * always reports `scrollHeight === clientHeight` — the page cannot scroll, by construction. On a
 * tall window nothing is lost. On a landscape tablet — the counter's everyday posture, not an edge
 * case — the box is 268px and the screen is worked through a slit:
 *
 *   hub#1730 (`.outlet`, no inner scroller)  → the content past 268px was UNREACHABLE.
 *   hub#1745 (the nine core surfaces)        → reachable, but the list is a 124px strip.
 *
 * Measured on the PRE bench (`banco-pre`) at 952x426, 2026-09-10, against `origin/develop`:
 *
 *   /apps       .fill 268px · shell scroller 300/300 (cannot scroll) · list 124/692  <- the bug
 *   /billing    .fill 268px · content wants 319px
 *   /employees  .fill 268px · content wants 254px (staff, roles, api keys, approvals)
 *   /api-docs   .hub-detail-shell--fill 334px (no tabbar) · content wants 6494px
 *
 * The floor has to clear the SHORT boxes so the shell's scroller takes over, and stay at or below
 * the phone's box so it is inert everywhere the layout already worked. Both are derived from the
 * shell's own CSS below, never remembered.
 */

/**
 * Ionic's own `--ion-padding` default, applied through the `ion-padding` class `AppPage` puts on
 * `ion-content`. It is the ONE piece of shell chrome the Hub does not declare, so it is named here
 * and guarded below: the day the theme overrides it, this number is silently wrong.
 */
const IONIC_CONTENT_PADDING_PX = 16;

/** Innermost `{ … }` blocks of a plain stylesheet, comments stripped. */
function cssRules(css: string): Array<{ selector: string; body: string }> {
  const rules: Array<{ selector: string; body: string }> = [];
  for (const block of stripCssComments(css).matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
    rules.push({ selector: block[1].trim().split('\n').pop()?.trim() ?? '', body: block[2] });
  }
  return rules;
}

/** The body of the one rule with this exact selector. Throws when the anchor is gone. */
function ruleBody(css: string, selector: string): string {
  const found = cssRules(css).filter((rule) => rule.selector === selector);
  if (found.length !== 1) {
    throw new Error(`expected exactly one \`${selector}\` rule, found ${found.length}`);
  }
  return found[0].body;
}

/** A px declaration inside a rule body. Throws when the declaration is gone. */
function pxDeclaration(body: string, property: string): number {
  const value = body.match(new RegExp(`(?<![-\\w])${property}:\\s*([\\d.]+)px`));
  if (!value) throw new Error(`\`${property}\` is no longer declared in px`);
  return Number(value[1]);
}

/**
 * hub#1745 — the chrome around the work surface, DERIVED from `polish.css`.
 *
 * It used to be `SHELL_CHROME_PX = 158`, a number measured once in a browser. A literal cannot
 * notice that the toolbar grew: the guard stayed green while the floor stopped clearing the real
 * box. These read the declarations the shell actually ships, so the box follows the CSS.
 */
const shellChrome = (css: string) => {
  const toolbar = ruleBody(css, 'ion-toolbar');
  return {
    header: pxDeclaration(toolbar, '--min-height'),
    padding: 2 * IONIC_CONTENT_PADDING_PX,
    // The secondary tabbar: an `ion-segment` of `ion-segment-button`s inside the footer toolbar.
    tabbar:
      pxDeclaration(ruleBody(css, 'ion-segment-button'), 'min-height') +
      2 * pxDeclaration(ruleBody(css, 'ion-segment'), 'padding') +
      pxDeclaration(toolbar, '--padding-top') +
      pxDeclaration(toolbar, '--padding-bottom'),
  };
};

/** Height `ion-content` gives a surface. `withTabbar: false` is a screen with no secondary tabs. */
function contentBoxPx(css: string, viewportHeight: number, withTabbar: boolean): number {
  const chrome = shellChrome(css);
  return viewportHeight - chrome.header - chrome.padding - (withTabbar ? chrome.tabbar : 0);
}

/** The floor every work surface shares. Its home is the Hub's own `:root` in `variables.css`. */
const WORK_SURFACE_TOKEN = '--ok-work-surface-min';

/** A `--ok-*` token of the Hub theme in px, or 0 when the theme declares no such token. */
function themeTokenPx(css: string, token: string): number {
  const value = css.match(new RegExp(`(?<![-\\w])${token}:\\s*([\\d.]+)(px|rem)`));
  if (!value) return 0;
  return value[2] === 'rem' ? Number(value[1]) * 16 : Number(value[1]);
}

/**
 * The `min-height` of a rule in px: 0 when it declares no floor at all, and ALSO 0 when it points
 * at a token the theme does not define. Resolving to 0 is deliberate — a floor nobody can resolve
 * is a floor that does not exist, and the guard has to go red for it, not shrug.
 */
function floorPx(body: string, themeCss: string): number {
  const floor = body.match(/(?<![-\w])min-height:\s*([^;]+)/);
  if (!floor) return 0;
  const value = floor[1].trim();
  const token = value.match(/^var\(\s*(--[\w-]+)\s*\)$/);
  if (token) return themeTokenPx(themeCss, token[1]);
  const literal = value.match(/^([\d.]+)(px|rem)$/);
  if (!literal) return 0;
  return literal[2] === 'rem' ? Number(literal[1]) * 16 : Number(literal[1]);
}

/**
 * Every rule that pins a screen to the shell's scroller: a bare single-class selector declaring
 * `height: 100%`, in a view that is NOT the centred `detail` layout (there the wrapper is
 * `AppPage`'s and `height: 100%` resolves against `auto`, so it pins nothing).
 *
 * It is a SWEEP and not a list of nine names on purpose: the tenth surface is born from copying
 * the ninth, and a list only ever guards the nine that were already broken.
 */
const SINGLE_CLASS = /^\.[A-Za-z][\w-]*$/;

function workSurfaces(): Array<{ where: string; selector: string; body: string }> {
  const surfaces: Array<{ where: string; selector: string; body: string }> = [];
  for (const name of listVue('views')) {
    const source = surfaceSource('views', name);
    if (source.includes('content-layout="detail"')) continue;
    for (const { selector, body } of styleRules(source)) {
      if (!SINGLE_CLASS.test(selector)) continue;
      if (!/(?<![-\w])height:\s*100%/.test(body)) continue;
      surfaces.push({ where: `views/${name}`, selector, body });
    }
  }
  // `detail-fill` (today: /api-docs) keeps the full height, and its wrapper is the shell's own.
  surfaces.push({
    where: 'theme/polish.css',
    selector: '.hub-detail-shell--fill',
    body: ruleBody(polishSource(), '.hub-detail-shell--fill'),
  });
  return surfaces;
}

describe('shell work surfaces on a short viewport', () => {
  it('hub#1745: the shell chrome is read from polish.css, not remembered', () => {
    // Positive control: move the tabbar in a COPY of the stylesheet and the box has to move with it.
    const taller = polishSource().replace('min-height: 46px;', 'min-height: 96px;');
    expect(shellChrome(taller).tabbar).toBe(shellChrome(polishSource()).tabbar + 50);
    expect(contentBoxPx(taller, 426, true)).toBe(contentBoxPx(polishSource(), 426, true) - 50);
    // …and a chrome anchor that disappears is an error, never a silent zero.
    expect(() => shellChrome(polishSource().replace('--min-height: 60px;', ''))).toThrow();
    // The Hub does not override Ionic's content padding; if it ever does, the constant above lies.
    expect(polishSource()).not.toMatch(/(?<![-\w])--ion-padding:/);
    expect(themeVariablesSource()).not.toMatch(/(?<![-\w])--ion-padding:/);
  });

  it('hub#1745: the derived chrome reproduces what the browser measured on the bench', () => {
    // The measurement of record (banco-pre, 2026-09-10) — see the comment above. If this fails the
    // chrome changed: re-measure on the bench and update BOTH, never just this line.
    const css = polishSource();
    expect(contentBoxPx(css, 426, true)).toBe(268); // tablet landscape, with tabbar
    expect(contentBoxPx(css, 426, false)).toBe(334); // …and without one (/api-docs)
    expect(contentBoxPx(css, 844, true)).toBe(686); // phone
    expect(contentBoxPx(css, 900, true)).toBe(742); // desktop
  });

  it('hub#1745: the floor detector reads the rule that regressed, the token, and a dead token', () => {
    const theme = themeVariablesSource();
    // The exact shape that shipped the bug — pinned, with no floor.
    expect(floorPx('height: 100%;', theme)).toBe(0);
    // The shape that fixes it, through the token…
    expect(floorPx(`height: 100%; min-height: var(${WORK_SURFACE_TOKEN});`, theme)).toBeGreaterThan(0);
    // …and a token nobody declares resolves to NO floor, so the sweep below goes red for it.
    expect(floorPx('height: 100%; min-height: var(--ok-nope);', theme)).toBe(0);
    // Literals still read, in either unit — the guard must not depend on the token to see a floor.
    expect(floorPx('min-height: 30rem;', theme)).toBe(480);
    expect(floorPx('min-height: 480px;', theme)).toBe(480);
  });

  it('hub#1745: the sweep finds every surface that pins itself to the shell scroller', () => {
    const found = workSurfaces().map(({ where, selector }) => `${where} ${selector}`);
    // Positive control: the ten surfaces measured on the bench are all in the sweep…
    expect(found).toEqual(
      expect.arrayContaining([
        'views/ModuleView.vue .outlet',
        'views/ApiDocsPage.vue .api-docs-wrap',
        'views/AppsPage.vue .fill',
        'views/ApiKeysPanel.vue .fill',
        'views/ApprovalsPanel.vue .fill',
        'views/BillingPage.vue .fill',
        'views/DashboardPage.vue .fill',
        'views/EmployeesPage.vue .fill',
        'views/RolesPanel.vue .fill',
        'theme/polish.css .hub-detail-shell--fill',
      ]),
    );
    // …and a card deep inside a centred `detail` screen is NOT a work surface: it pins nothing.
    expect(found).not.toContain('views/ProfilePage.vue .profile-card');
    expect(found).not.toContain('views/SystemPage.vue .metric-card');
  });

  it('hub#1745: every work surface overflows ion-content on a short viewport, so the shell scrolls', () => {
    const theme = themeVariablesSource();
    const css = polishSource();
    // A screen with no secondary tabbar keeps a TALLER box, so that is the one the floor must clear.
    const shortest = contentBoxPx(css, 426, false);
    const tooShort = workSurfaces()
      .filter(({ body }) => floorPx(body, theme) <= shortest)
      .map(({ where, selector, body }) => `${where} ${selector} → ${floorPx(body, theme)}px`);
    expect(tooShort).toEqual([]);
  });

  it('hub#1745: the floor stays inert on the viewports that already fitted', () => {
    // An over-correction is its own regression: a floor taller than the phone's box would force a
    // scroll on every device instead of only where the content did not fit.
    const theme = themeVariablesSource();
    const phoneBox = contentBoxPx(polishSource(), 844, true);
    for (const { where, selector, body } of workSurfaces()) {
      expect(`${where} ${selector} → ${floorPx(body, theme)}`).toBe(
        `${where} ${selector} → ${Math.min(floorPx(body, theme), phoneBox)}`,
      );
    }
  });

  it('hub#1745: the floor is ONE token, so the tenth surface cannot be born with its own number', () => {
    const bare = workSurfaces().filter(
      ({ body }) => !/(?<![-\w])min-height:\s*var\(--ok-work-surface-min\)/.test(body),
    );
    expect(bare.map(({ where, selector }) => `${where} ${selector}`)).toEqual([]);
    // The token's home is the Hub's own `:root`, next to the other `--ok-*` design tokens — no new
    // namespace and no OutfitKit bump, which is what made extracting it cheap enough to do now.
    expect(themeVariablesSource()).toMatch(
      new RegExp(`${WORK_SURFACE_TOKEN}:\\s*[\\d.]+(px|rem);`),
    );
  });

  it('hub#1730: the surface keeps the DEFINED height that `ok-data-table[fill]` constrains against', () => {
    // Swapping `height` for `min-height` would fix the clipping and break every `fill` table:
    // their `:host{height:100%}` would resolve against `auto` again (the regression the `.outlet`
    // rule's own comment documents). The contract is BOTH: a definite height AND a floor under it.
    for (const { where, selector, body } of workSurfaces()) {
      expect(`${where} ${selector}: ${/(?<![-\w])height:\s*100%/.test(body)}`).toBe(
        `${where} ${selector}: true`,
      );
    }
  });
});
