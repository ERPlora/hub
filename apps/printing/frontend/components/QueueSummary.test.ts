// «Print queue» on the Printers page (PRINTING-F01): one card per role that has a printer or jobs (a new
// business sees none), with its state and what waits; an orange alert when a role has jobs waiting for
// over a minute and no active printer; «All clear» with nothing waiting; the read's failure with «Retry».
import { afterEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountPrinting, words } from '../__tests__/mount-printing';
import type { JobSummaryOut, UsageSummary } from '../operations';
import QueueSummary from './QueueSummary.vue';

const OP = 'printing.job.summary';
const ago = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

const usage = (name: UsageSummary['usage'], more: Partial<UsageSummary> = {}): UsageSummary => ({
  usage: name,
  printers: 0,
  default_printer: null,
  prints_on: null,
  pending: 0,
  oldest_pending_at: null,
  sent: 0,
  failed: 0,
  unattended: 0,
  stalled: 0,
  ...more,
});

function summary(...usages: UsageSummary[]): JobSummaryOut {
  const all = (['receipt', 'kitchen', 'bar', 'label'] as const).map((name) => usages.find((u) => u.usage === name) ?? usage(name));
  const total = (key: 'pending' | 'sent' | 'failed') => all.reduce((n, u) => n + u[key], 0);
  return { usages: all, pending: total('pending'), sent: total('sent'), failed: total('failed') };
}

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountPrinting(QueueSummary, { locale });
  await m.live();
  return m;
}

describe('QueueSummary', () => {
  it('a new business sees no card and that all is clear', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    expect(s.find('printing-summary-heading').text()).toBe('Print queue');
    await s.result(OP, summary());
    expect(s.wrapper.findAll('[data-testid^="printing-summary-card-"]')).toHaveLength(0);
    expect(s.find('printing-summary-all-clear').text()).toBe('All clear: nothing is waiting in the queue.');
  });

  it('a card per role with printers or jobs: its state, what waits and where it prints', async () => {
    const s = await setup();
    await s.result(
      OP,
      summary(
        usage('receipt', { printers: 1, default_printer: 'Till', prints_on: 'Till', pending: 2, oldest_pending_at: ago(3) }),
        usage('kitchen', { printers: 1, failed: 1 }),
        usage('label', { pending: 1, oldest_pending_at: ago(0) }),
      ),
    );
    expect(s.wrapper.findAll('[data-testid^="printing-summary-card-"]').map((c) => c.attributes('data-testid'))).toEqual([
      'printing-summary-card-receipt',
      'printing-summary-card-kitchen',
      'printing-summary-card-label',
    ]);
    expect(words(s.find('printing-summary-card-receipt').element)).toBe('Receipt Ready Waiting: 2 · the oldest has waited 3 min Prints on: Till.');
    expect(words(s.find('printing-summary-card-kitchen').element)).toBe('Kitchen With errors Nothing waiting Failed: 1');
    expect(words(s.find('printing-summary-card-label').element)).toContain('Waiting, no printer');
    expect(s.find('printing-summary-all-clear').exists()).toBe(false);
  });

  it('names the printer each role prints on even when none was chosen (hub#1527)', async () => {
    const s = await setup('es');
    await s.result(OP, summary(usage('receipt', { printers: 2, prints_on: 'Caja' }), usage('kitchen', { printers: 1, prints_on: 'Plancha', default_printer: 'Plancha' })));
    expect(words(s.find('printing-summary-card-receipt').element)).toBe('Recibo Listo Nada en cola Imprime en: Caja.');
    expect(words(s.find('printing-summary-card-kitchen').element)).toBe('Cocina Listo Nada en cola Imprime en: Plancha.');
  });

  it('warns when a role without printer has waited over a minute', async () => {
    const s = await setup('es');
    await s.result(OP, summary(usage('kitchen', { pending: 3, oldest_pending_at: ago(4) }), usage('label', { pending: 1, oldest_pending_at: ago(0) })));
    expect(words(s.find('printing-summary-alert-kitchen').element)).toBe(
      '3 trabajos de impresión de Cocina llevan 4 min esperando. Ninguna impresora activa tiene esta función: añade una abajo o dale esta función a una de ellas.',
    );
    expect(s.find('printing-summary-alert-label').exists()).toBe(false);
  });

  it('says the read failed and retries it', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'printing.boom'));
    await flush();
    expect(s.find('printing-summary-error').text()).toContain('Could not read the print queue.');
    expect(s.find('printing-summary-all-clear').exists()).toBe(false);
    expect(s.find('printing-summary-retry').exists()).toBe(true);
  });

  it('a job a device has and has not confirmed is not «All clear»', async () => {
    const s = await setup();
    await s.result(OP, summary(usage('receipt', { printers: 1, sent: 1 })));
    expect(s.find('printing-summary-all-clear').exists()).toBe(false);
  });
});

describe('QueueSummary by the clock', () => {
  afterEach(() => vi.useRealTimers());

  it('the ages and the alert move on by themselves, without another result', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    vi.setSystemTime(new Date('2026-10-15T08:00:00Z'));
    const s = await setup();
    const waiting = summary(usage('label', { pending: 1, oldest_pending_at: '2026-10-15T07:59:30Z' }));
    // The card's own reading by the clock (below) answers what the server has: the same.
    s.net.onApi(() => Response.json(waiting));
    await s.result(OP, waiting);
    expect(s.find('printing-summary-alert-label').exists()).toBe(false);
    expect(words(s.find('printing-summary-card-label').element)).toContain('the oldest has waited 30 s');
    vi.advanceTimersByTime(30_000);
    await flush();
    expect(words(s.find('printing-summary-alert-label').element)).toContain('1 print job for Label has been waiting 1 min.');
    expect(words(s.find('printing-summary-card-label').element)).toContain('the oldest has waited 1 min');
  });

  it('a role whose jobs no device set up here can print says so, not «Ready», and where to fix it', async () => {
    // The bell's «Nothing is printing “Receipt”» leads here (PRINTING-F01): the card says why.
    const s = await setup('es');
    await s.result(OP, summary(usage('receipt', { printers: 1, prints_on: 'Caja', pending: 1, oldest_pending_at: ago(0), unattended: 1 })));
    const card = words(s.find('printing-summary-card-receipt').element);
    expect(card).toMatch(/^Recibo Sin dispositivo /);
    expect(card).not.toContain('Listo');
    expect(s.find('printing-summary-no-device-receipt').text()).toBe(
      'Ningún dispositivo dado de alta lo imprime: dalo de alta en Dispositivos.',
    );
    await s.result(OP, summary(usage('receipt', { printers: 1, prints_on: 'Caja', pending: 1, oldest_pending_at: ago(0) })));
    expect(words(s.find('printing-summary-card-receipt').element)).toMatch(/^Recibo Listo /);
    expect(s.wrapper.find('[data-testid="printing-summary-no-device-receipt"]').exists()).toBe(false);
  });

  it('a role whose device set up is off says so, not «Ready», and what to do', async () => {
    // The bell rings for it too (FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF): a minute in the queue, its device quiet.
    const s = await setup('es');
    await s.result(OP, summary(usage('receipt', { printers: 1, prints_on: 'Caja', pending: 1, oldest_pending_at: ago(2), stalled: 1 })));
    const card = words(s.find('printing-summary-card-receipt').element);
    expect(card).toMatch(/^Recibo Dispositivo apagado /);
    expect(card).not.toContain('Listo');
    expect(s.find('printing-summary-device-off-receipt').text()).toBe(
      'El dispositivo que lo imprime no responde: enciéndelo y abre en él la app de ERPlora.',
    );
    expect(s.wrapper.find('[data-testid="printing-summary-no-device-receipt"]').exists()).toBe(false);
    // None set up at all: «set one up» says it, not «switch it on».
    await s.result(OP, summary(usage('receipt', { printers: 1, prints_on: 'Caja', pending: 1, oldest_pending_at: ago(2), unattended: 1, stalled: 1 })));
    expect(words(s.find('printing-summary-card-receipt').element)).toMatch(/^Recibo Sin dispositivo /);
    expect(s.wrapper.find('[data-testid="printing-summary-device-off-receipt"]').exists()).toBe(false);
  });

  it('says the device is off in English too', async () => {
    const s = await setup();
    await s.result(OP, summary(usage('kitchen', { printers: 1, pending: 1, oldest_pending_at: ago(2), stalled: 1 })));
    expect(words(s.find('printing-summary-card-kitchen').element)).toMatch(/^Kitchen Device off /);
    expect(s.find('printing-summary-device-off-kitchen').text()).toBe(
      'The device that prints it is not responding: switch it on and open the ERPlora app on it.',
    );
  });
});

describe('QueueSummary reads the summary again by the clock', () => {
  // FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF: «Device off» moves as time passes (a job reaching its minute, a device
  // going quiet for 90 s) with no event to re-run the live query. While something waits and the page is in sight, the
  // card reads `printing.job.summary` once every 30 s, the bell's pace (HubBell.vue): a reading older than a live result
  // that came meanwhile is dropped, one that fails keeps the last. The fake timers are the test's only.
  const SUMMARY = '/api/printing/jobs/summary';
  const waitingOn = (more: Partial<UsageSummary> = {}) =>
    summary(usage('receipt', { printers: 1, prints_on: 'Till', pending: 1, oldest_pending_at: ago(2), ...more }));

  async function clocked(answer: (call: number) => Response | Promise<Response>) {
    let calls = 0;
    const s = await setup();
    s.net.onApi(() => answer(++calls));
    const reads = () => s.net.api.filter((call) => call.url.startsWith(SUMMARY)).length;
    const tick = async (ms: number) => {
      vi.advanceTimersByTime(ms);
      await flush();
    };
    const state = () => words(s.find('printing-summary-card-receipt').element);
    return { ...s, reads, tick, state };
  }

  function withFakeTimers(test: () => Promise<void>) {
    return async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['setTimeout', 'setInterval', 'clearTimeout', 'clearInterval'] });
      try {
        await test();
      } finally {
        vi.useRealTimers();
      }
    };
  }

  it(
    'with something waiting, the card turns «Device off» by itself, with no event and no new stream',
    withFakeTimers(async () => {
      const s = await clocked(() => Response.json(waitingOn({ stalled: 1 })));
      await s.result(OP, waitingOn());
      expect(s.state()).toMatch(/^Receipt Ready /);
      const streams = s.net.streams.length;

      await s.tick(29_000);
      expect(s.reads()).toBe(0);
      await s.tick(1_000);
      expect(s.reads()).toBe(1);
      expect(s.state()).toMatch(/^Receipt Device off /);
      expect(s.find('printing-summary-device-off-receipt').exists()).toBe(true);
      expect(s.net.streams.length).toBe(streams);
      await s.tick(30_000);
      expect(s.reads()).toBe(2);
    }),
  );

  it(
    'and back to «Ready» when the device is there again',
    withFakeTimers(async () => {
      const s = await clocked(() => Response.json(waitingOn()));
      await s.result(OP, waitingOn({ stalled: 1 }));
      expect(s.state()).toMatch(/^Receipt Device off /);
      await s.tick(30_000);
      expect(s.state()).toMatch(/^Receipt Ready /);
    }),
  );

  it(
    'with nothing waiting nothing can change by the clock: it reads nothing',
    withFakeTimers(async () => {
      const s = await clocked(() => Response.json(summary()));
      await s.result(OP, summary(usage('receipt', { printers: 1, prints_on: 'Till' })));
      await s.tick(5 * 60_000);
      expect(s.reads()).toBe(0);
    }),
  );

  it(
    'a reading that fails keeps the last summary, and one older than a live result does not undo it',
    withFakeTimers(async () => {
      let release: (response: Response) => void = () => undefined;
      const s = await clocked((call) =>
        call === 1 ? new Response('{}', { status: 500 }) : new Promise<Response>((resolve) => (release = resolve)),
      );
      await s.result(OP, waitingOn({ stalled: 1 }));
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      await s.tick(30_000);
      expect(s.state()).toMatch(/^Receipt Device off /);
      expect(s.find('printing-summary-error').exists()).toBe(false);
      expect(warn).toHaveBeenCalled();
      warn.mockRestore();

      await s.tick(30_000); // the second reading is on its way…
      await s.result(OP, waitingOn({ failed: 1 }), {}, 2);
      release(Response.json(waitingOn({ stalled: 1 })));
      await flush();
      expect(s.state()).toMatch(/^Receipt With errors /);
    }),
  );

  it(
    'reads nothing while the page is hidden, nor once it is gone',
    withFakeTimers(async () => {
      const s = await clocked(() => Response.json(waitingOn()));
      await s.result(OP, waitingOn());
      const hidden = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
      try {
        await s.tick(60_000);
        expect(s.reads()).toBe(0);
      } finally {
        hidden.mockRestore();
      }
      await s.tick(30_000);
      expect(s.reads()).toBe(1);
      s.wrapper.unmount();
      await s.tick(5 * 60_000);
      expect(s.reads()).toBe(1);
    }),
  );
});
