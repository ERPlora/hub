import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const viewSource = (name: string): string =>
  readFileSync(new URL(`./${name}`, import.meta.url), 'utf8');

const appPageSource = (): string =>
  readFileSync(new URL('../components/AppPage.vue', import.meta.url), 'utf8');

const polishSource = (): string =>
  readFileSync(new URL('../theme/polish.css', import.meta.url), 'utf8');

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

  it('uses the same centered 72rem contract as the Cloud dashboard', () => {
    const source = polishSource();
    expect(source).toMatch(/\.hub-detail-shell\s*\{[\s\S]*?width:\s*min\(100%, 72rem\)/);
    expect(source).toMatch(/\.hub-detail-shell\s*\{[\s\S]*?min-width:\s*0/);
    expect(source).toMatch(/\.hub-detail-shell\s*\{[\s\S]*?margin-inline:\s*auto/);
    expect(source).toMatch(/\.hub-detail-shell--fill\s*\{[\s\S]*?height:\s*100%/);
  });
});
