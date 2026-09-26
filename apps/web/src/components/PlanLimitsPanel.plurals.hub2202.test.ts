// hub#2202 — with one device signed in, the plan card read «1 sesiones activas»: the counters of
// «Plan & limits» were a single sentence for every number. vue-i18n picks the branch of a
// `singular | plural` message from the `n` of the named options, which is exactly how the panel
// calls them, so the check runs the REAL catalogues through that same call shape.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { createI18n } from 'vue-i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const source = readFileSync(new URL('./PlanLimitsPanel.vue', import.meta.url), 'utf8');

function translate(locale: 'en' | 'es', key: string, n: number): string {
  const i18n = createI18n({ legacy: false, locale, messages: { en, es } });
  return i18n.global.t(key, { n });
}

describe('Plan & limits counters agree with their number (hub#2202)', () => {
  it('the panel passes the count as `n`, the option vue-i18n pluralises on', () => {
    expect(source).toContain("t('planLimits.activeSessions', { n: metrics.sessions.active })");
    expect(source).toContain("t('planLimits.activeUsers', { n: metrics.users.active })");
  });

  it.each([
    ['es', 'planLimits.activeSessions', 1, '1 sesión activa'],
    ['es', 'planLimits.activeSessions', 2, '2 sesiones activas'],
    ['es', 'planLimits.activeSessions', 0, '0 sesiones activas'],
    ['en', 'planLimits.activeSessions', 1, '1 active session'],
    ['en', 'planLimits.activeSessions', 3, '3 active sessions'],
    ['es', 'planLimits.activeUsers', 1, '1 persona activa'],
    ['es', 'planLimits.activeUsers', 4, '4 personas activas'],
    ['en', 'planLimits.activeUsers', 1, '1 active person'],
    ['en', 'planLimits.activeUsers', 4, '4 active people'],
  ] as const)('%s · %s with %i reads «%s»', (locale, key, n, expected) => {
    expect(translate(locale, key, n)).toBe(expected);
  });
});
