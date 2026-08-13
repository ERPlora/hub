// @vitest-environment node
// hub#863 — the Activity tab's last two hardcoded strings.
//
// The panel hardcoded Spanish in two places instead of going through i18n: the activity search
// placeholder and the status badge («Completada»/«Pendiente»). It is the inverse of hub#768
// (English leaking into a Spanish surface): here Spanish leaked into the code. Both halves break
// the same rule — English is the source language and every visible string goes through i18n
// (ADR-0055/0199). A hardcoded string cannot be translated, so the moment the app is served in
// another language those two stay in Spanish forever.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import en from './locales/en';
import es from './locales/es';

type Catalogue = { dashboard: Record<string, string> };

const EN = (en as unknown as Catalogue).dashboard;
const ES = (es as unknown as Catalogue).dashboard;

describe('the Activity tab speaks through i18n (hub#863)', () => {
  it('has the search placeholder in both catalogues, English as source', () => {
    expect(EN.activitySearchPlaceholder).toBe('Search activity…');
    expect(ES.activitySearchPlaceholder).toBe('Buscar actividad…');
  });

  it('has both status badges in both catalogues, English as source', () => {
    // «Completada»/«Pendiente» agree with «venta» — the row is a sale.
    expect(EN.activityStatusCompleted).toBe('Completed');
    expect(ES.activityStatusCompleted).toBe('Completada');
    expect(EN.activityStatusPending).toBe('Pending');
    expect(ES.activityStatusPending).toBe('Pendiente');
  });

  it('leaves no Spanish literal behind in DashboardPage.vue', () => {
    // The regression this suite exists for: the string moving BACK into the template. The view
    // may only reach these words through `t('dashboard.…')`.
    const source = readFileSync(
      resolve(__dirname, '../views/DashboardPage.vue'),
      'utf8',
    );
    expect(source).not.toContain('Buscar actividad');
    expect(source).not.toMatch(/'Completada'|'Pendiente'/);
  });
});
