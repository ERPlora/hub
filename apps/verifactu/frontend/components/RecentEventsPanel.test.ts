// «Recent AEAT events», VeriFactu's panel of the Home (FIX-VERIFACTU-SETUP-HOOKS; the old module's
// `erp-verifactu-events-widget`): the latest events of `verifactu.stats.events_recent`, followed live, each with its
// moment, its type in the reader's language — never its code (gh:verifactu#139) — and the sentence the server
// composes; its states of loading, nothing yet and failure. The panel's frame (title, icon) is base's WidgetPanel.
import { formatDateTime } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountVerifactu } from '../__tests__/mount-verifactu';
import type { EventOut } from '../operations';
import RecentEventsPanel from './RecentEventsPanel.vue';

const OP = 'verifactu.stats.events_recent';

const DEFERRED: EventOut = {
  id: 'e2',
  created_at: '2026-10-23T09:15:00Z',
  kind: 'deferred',
  severity: 'warning',
  message: 'Submission of F2 T-2026-0007 postponed: the AEAT asks to wait 60 s.',
  record_id: 'r7',
  invoice_number: 'T-2026-0007',
};
const CREATED: EventOut = {
  id: 'e1',
  created_at: '2026-10-23T09:14:00Z',
  kind: 'record_created',
  severity: 'info',
  message: 'Record F2 T-2026-0007 sealed.',
  record_id: 'r7',
  invoice_number: 'T-2026-0007',
};

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountVerifactu(RecentEventsPanel, { path: '/', locale });
  await m.live();
  const entries = () =>
    m.wrapper.findAll('[data-testid="verifactu-events-panel-entry"]').map((entry) => ({
      time: entry.find('[data-testid="verifactu-events-panel-time"]').text(),
      title: entry.find('[data-testid="verifactu-events-panel-type"]').text(),
      description: entry.find('[data-testid="verifactu-events-panel-message"]').text(),
      severity: entry.attributes('data-severity'),
    }));
  return { ...m, entries };
}

describe('RecentEventsPanel', () => {
  it('follows the latest eight events', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 8 }]);
  });

  it('says it is loading until the first result', async () => {
    const s = await setup();
    expect(s.find('verifactu-events-panel-loading').text()).toBe('Loading…');
    expect(s.entries()).toEqual([]);
  });

  it('names each event by its type in the reader’s language, never its code, with its moment and its sentence', async () => {
    const s = await setup();
    await s.result(OP, { rows: [DEFERRED, CREATED] });
    expect(s.entries()).toEqual([
      { time: formatDateTime(DEFERRED.created_at, 'en'), title: 'Submission postponed', description: DEFERRED.message, severity: 'warning' },
      { time: formatDateTime(CREATED.created_at, 'en'), title: 'Record created', description: CREATED.message, severity: 'info' },
    ]);
    expect(s.wrapper.text()).not.toContain('deferred');
    expect(s.wrapper.text()).not.toContain('record_created');
  });

  it('speaks Spanish to a Spanish reader', async () => {
    const s = await setup('es');
    await s.result(OP, { rows: [DEFERRED] });
    expect(s.entries().map((entry) => [entry.title, entry.time])).toEqual([
      ['Envío aplazado', formatDateTime(DEFERRED.created_at, 'es')],
    ]);
  });

  it('follows itself: a newer result replaces what it painted', async () => {
    const s = await setup();
    await s.result(OP, { rows: [CREATED] });
    await s.result(OP, { rows: [DEFERRED, CREATED] }, {}, 2);
    expect(s.entries().map((entry) => entry.title)).toEqual(['Submission postponed', 'Record created']);
  });

  it('says «No events.» when there are none yet', async () => {
    const s = await setup();
    await s.result(OP, { rows: [] });
    expect(s.find('verifactu-events-panel-empty').text()).toBe('No events.');
  });

  it('says it could not load them, never the list it had, when the read fails', async () => {
    const s = await setup('es');
    await s.result(OP, { rows: [CREATED] });
    s.net.lastStream().push(errorFrame(s.subId(OP), 'permission_denied'));
    await flush();
    expect(s.find('verifactu-events-panel-error').text()).toBe('No se han podido cargar los últimos eventos de la AEAT.');
    expect(s.entries()).toEqual([]);
  });
});
