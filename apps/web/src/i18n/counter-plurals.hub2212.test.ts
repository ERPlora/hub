// hub#2212 — several notices put a number in front of a noun that was always plural, or patched
// it with «(s)»: «1 filas eliminadas», «1 evento(s)…», «Vas a borrar 1 registros», «durante 1
// minutos». Same recipe as the plan card (hub#2202): each message carries `singular | plural` and
// the caller passes the number as `n` or `count`, the two named options vue-i18n picks the branch
// from. The check runs the REAL catalogues through that call shape, and pins the call sites so a
// caller renaming the option (e.g. back to `{ total }`) cannot silently lose the singular.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { createI18n } from 'vue-i18n';
import en from './locales/en';
import es from './locales/es';

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8');
}

function translate(locale: 'en' | 'es', key: string, named: Record<string, number>): string {
  const i18n = createI18n({ legacy: false, locale, messages: { en, es } });
  return i18n.global.t(key, named);
}

describe('counters agree with their number (hub#2212)', () => {
  it.each([
    ['../components/AppTopbar.vue', "t('topbar.deadLettersBody', { count: deadLetterCount })"],
    ['../components/AppTopbar.vue', 'count: station.waiting,'],
    ['../components/AssistantDrawer.vue', "t('assistant.confirmBulkAffected', { count: gate.affected })"],
    ['../components/PinPolicyCard.vue', "t('pinPolicy.idleMinutesConsequence', { n: IDLE_STOPS[stop.value] })"],
    ['../components/ResetPanel.vue', "t('settings.resetDeleted', { n: r.rows_deleted })"],
    ['../components/ResetPanel.vue', "t('settings.resetUndoBody', { n: batch.rows })"],
    ['../components/ResetPanel.vue', "t('settings.resetConfirmBody', { n: total })"],
    ['../views/SystemPage.vue', "t('system.retryAllDone', { count: moved })"],
    ['../components/ModulePlanPanel.vue', "t('modulePlan.trialDays', { n: tier.trial_days })"],
  ] as const)('%s passes the number as `n`/`count`: %s', (file, call) => {
    expect(source(file)).toContain(call);
  });

  it.each([
    ['es', 'topbar.deadLettersBody', { count: 1 }, 'Hay 1 evento que el relay no pudo entregar. Revísalo y reenvíalo.'],
    [
      'es',
      'topbar.deadLettersBody',
      { count: 3 },
      'Hay 3 eventos que el relay no pudo entregar. Revísalos y reenvíalos.',
    ],
    ['en', 'topbar.deadLettersBody', { count: 1 }, '1 event the relay could not deliver. Review and resend it.'],
    ['en', 'topbar.deadLettersBody', { count: 3 }, '3 events the relay could not deliver. Review and resend them.'],
    [
      'es',
      'topbar.printingStalledBody',
      { count: 1, minutes: 4 },
      'Hay 1 documento esperando desde hace 4 min. Comprueba que la caja que imprime ahí está encendida.',
    ],
    [
      'es',
      'topbar.printingStalledBody',
      { count: 2, minutes: 4 },
      'Hay 2 documentos esperando desde hace 4 min. Comprueba que la caja que imprime ahí está encendida.',
    ],
    [
      'en',
      'topbar.printingStalledBody',
      { count: 1, minutes: 4 },
      '1 document waiting for 4 min. Check the till that prints there is on.',
    ],
    [
      'en',
      'topbar.printingStalledBody',
      { count: 2, minutes: 4 },
      '2 documents waiting for 4 min. Check the till that prints there is on.',
    ],
    ['es', 'assistant.confirmBulkAffected', { count: 1 }, 'Vas a borrar 1 registro.'],
    ['es', 'assistant.confirmBulkAffected', { count: 7 }, 'Vas a borrar 7 registros.'],
    ['en', 'assistant.confirmBulkAffected', { count: 1 }, 'You are about to delete 1 record.'],
    ['en', 'assistant.confirmBulkAffected', { count: 7 }, 'You are about to delete 7 records.'],
    [
      'es',
      'pinPolicy.idleMinutesConsequence',
      { n: 1 },
      'Una caja que nadie toca durante 1 minuto cierra la sesión y muestra el pinpad: la siguiente venta lleva el nombre de la siguiente persona.',
    ],
    [
      'es',
      'pinPolicy.idleMinutesConsequence',
      { n: 5 },
      'Una caja que nadie toca durante 5 minutos cierra la sesión y muestra el pinpad: la siguiente venta lleva el nombre de la siguiente persona.',
    ],
    [
      'en',
      'pinPolicy.idleMinutesConsequence',
      { n: 1 },
      'A till nobody has touched for 1 minute signs the user out and shows the PIN pad, so the next sale carries the next person’s name.',
    ],
    [
      'en',
      'pinPolicy.idleMinutesConsequence',
      { n: 5 },
      'A till nobody has touched for 5 minutes signs the user out and shows the PIN pad, so the next sale carries the next person’s name.',
    ],
    ['es', 'settings.resetDeleted', { n: 1 }, '1 fila borrada'],
    ['es', 'settings.resetDeleted', { n: 12 }, '12 filas borradas'],
    ['en', 'settings.resetDeleted', { n: 1 }, '1 row deleted'],
    ['en', 'settings.resetDeleted', { n: 12 }, '12 rows deleted'],
    [
      'es',
      'settings.resetUndoBody',
      { n: 1 },
      'Se borrará la fila que trajo este blueprint. Lo que creaste después se conserva.',
    ],
    [
      'es',
      'settings.resetUndoBody',
      { n: 40 },
      'Se borrarán las 40 filas que trajo este blueprint. Lo que creaste después se conserva.',
    ],
    [
      'en',
      'settings.resetUndoBody',
      { n: 1 },
      '1 row brought in by this blueprint will be deleted. What you created afterwards is kept.',
    ],
    [
      'en',
      'settings.resetUndoBody',
      { n: 40 },
      '40 rows brought in by this blueprint will be deleted. What you created afterwards is kept.',
    ],
    ['es', 'settings.resetConfirmBody', { n: 1 }, 'Se borrará definitivamente 1 fila:'],
    ['es', 'settings.resetConfirmBody', { n: 9 }, 'Se borrarán definitivamente 9 filas:'],
    ['en', 'settings.resetConfirmBody', { n: 1 }, '1 row will be permanently deleted:'],
    ['en', 'settings.resetConfirmBody', { n: 9 }, '9 rows will be permanently deleted:'],
    ['es', 'system.retryAllDone', { count: 1 }, '1 evento reenviado al relay.'],
    ['es', 'system.retryAllDone', { count: 6 }, '6 eventos reenviados al relay.'],
    ['en', 'system.retryAllDone', { count: 1 }, '1 event resent to the relay.'],
    ['en', 'system.retryAllDone', { count: 6 }, '6 events resent to the relay.'],
    ['es', 'modulePlan.trialDays', { n: 1 }, '1 día de prueba'],
    ['es', 'modulePlan.trialDays', { n: 14 }, '14 días de prueba'],
    ['en', 'modulePlan.trialDays', { n: 1 }, '1-day trial'],
    ['en', 'modulePlan.trialDays', { n: 14 }, '14-day trial'],
  ] as const)('%s · %s with %o reads «%s»', (locale, key, named, expected) => {
    expect(translate(locale, key, named)).toBe(expected);
  });
});
