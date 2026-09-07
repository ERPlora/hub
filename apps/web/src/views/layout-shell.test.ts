import { readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const viewSource = (name: string): string =>
  readFileSync(new URL(`./${name}`, import.meta.url), 'utf8');

const appPageSource = (): string =>
  readFileSync(new URL('../components/AppPage.vue', import.meta.url), 'utf8');

const polishSource = (): string =>
  readFileSync(new URL('../theme/polish.css', import.meta.url), 'utf8');

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
    for (const block of style[1].matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
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
