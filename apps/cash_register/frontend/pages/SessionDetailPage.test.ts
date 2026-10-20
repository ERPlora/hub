// Cash register → the detail of a session (CASH_REGISTER-F11, F16; the old `erp-cashregister-session-
// detail`): «Session detail · S-…» with Back, the summary, the session's movements and counts, and
// «Print» (the X or Z report to the receipt printer's queue, or through the browser when Printing is not
// on). A session that does not exist says so; a failed read offers to retry. Everything re-runs by itself.
import { AppPage, toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, mountCash } from '../__tests__/mount-cash-register';
import { SESSION } from '../components/__tests__/session';
import ClosingReport from '../components/ClosingReport.vue';
import SessionCounts from '../components/SessionCounts.vue';
import SessionLines from '../components/SessionLines.vue';
import SessionSummary from '../components/SessionSummary.vue';
import * as print from '../lib/print';
import SessionDetailPage from './SessionDetailPage.vue';

const OP = 'cash_register.session.get';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
});

const QUEUED = { report: 'z', queued: true, job_id: 'j1', printer: 'Counter' };
const BROWSER = { report: 'z', queued: false, job_id: null, printer: null };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCash(SessionDetailPage, { path: '/cash_register/sessions/s1', props: { id: 's1' }, locale });
  await m.live();
  return m;
}

describe('SessionDetailPage', () => {
  it('reads the session of its address, under Cash register’s tabs with Back to the sessions', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ session_id: 's1' }]);
    const page = m.wrapper.findComponent(AppPage);
    expect(page.props('backHref')).toBe('/cash_register/sessions');
    expect((page.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['sessions', 'settings']);
    expect(m.find('cash-register-detail-loading').exists()).toBe(true);
  });

  it('shows the summary, the movements and the counts of the session', async () => {
    const m = await setup();
    await m.result(OP, SESSION);
    expect(m.find('cash-register-detail-title').text()).toBe('Session detail · S-261014-0001');
    expect(m.wrapper.findComponent(SessionSummary).props('session')).toEqual(SESSION);
    expect(m.wrapper.findComponent(SessionLines).props('query')).toEqual({ session_id: 's1' });
    expect(m.wrapper.findComponent(SessionCounts).props('sessionId')).toBe('s1');
    expect(m.wrapper.findComponent(ClosingReport).props('session')).toEqual(SESSION);
  });

  it('«Print» sends the report to the receipt printer and says where (CASH_REGISTER-F16)', async () => {
    const m = await setup();
    await m.result(OP, SESSION);
    const printed = vi.spyOn(print, 'printPaper').mockImplementation(() => {});
    m.answer(200, QUEUED);
    await click(m.find('cash-register-detail-print').element);
    expect(m.sent()).toEqual([{ method: 'POST', path: '/api/cash_register/sessions/print', query: {}, body: { session_id: 's1' } }]);
    expect(vi.mocked(toastSuccess)).toHaveBeenCalledWith('Report sent to the printer Counter.');
    expect(printed).not.toHaveBeenCalled();
  });

  it('with no printer chosen it goes to the first receipt printer', async () => {
    const m = await setup();
    await m.result(OP, SESSION);
    m.answer(200, { ...QUEUED, printer: null });
    await click(m.find('cash-register-detail-print').element);
    expect(vi.mocked(toastSuccess)).toHaveBeenCalledWith('Report sent to the receipt printer.');
  });

  it('without Printing on in the business the browser prints the report alone', async () => {
    const m = await setup();
    await m.result(OP, SESSION);
    const printed = vi.spyOn(print, 'printPaper').mockImplementation(() => {});
    m.answer(200, BROWSER);
    await click(m.find('cash-register-detail-print').element);
    expect(printed).toHaveBeenCalledOnce();
    expect((printed.mock.calls[0][0] as HTMLElement).dataset.testid).toBe('cash-register-report');
    expect(vi.mocked(toastSuccess)).not.toHaveBeenCalled();
  });

  it('a refusal says «Could not print» with the server\'s words, and nothing prints', async () => {
    const m = await setup();
    await m.result(OP, SESSION);
    const printed = vi.spyOn(print, 'printPaper').mockImplementation(() => {});
    m.answer(409, { error: { code: 'printing.no_printer', message: 'There is no receipt printer.' } });
    await click(m.find('cash-register-detail-print').element);
    expect(vi.mocked(toastError)).toHaveBeenCalledWith('Could not print. There is no receipt printer.');
    expect(printed).not.toHaveBeenCalled();
  });

  it('a print the browser refuses is said', async () => {
    const m = await setup();
    await m.result(OP, SESSION);
    vi.spyOn(print, 'printPaper').mockImplementation(() => {
      throw new Error('blocked');
    });
    m.answer(200, BROWSER);
    await click(m.find('cash-register-detail-print').element);
    expect(vi.mocked(toastError)).toHaveBeenCalledWith('Could not print.');
  });

  it('a blind count hides «Print» on an open session from whoever may not see the expected', async () => {
    const m = await setup();
    await m.result(OP, { ...SESSION, status: 'open', expected_hidden: true });
    expect(m.find('cash-register-detail-print').exists()).toBe(false);
    await m.result(OP, { ...SESSION, status: 'open', expected_hidden: false }, {}, 2);
    expect(m.find('cash-register-detail-print').exists()).toBe(true);
  });

  it('the paper says the time it was printed, not the time the page opened', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    try {
      vi.setSystemTime(new Date(2026, 9, 14, 10, 0));
      const m = await setup();
      await m.result(OP, SESSION);
      vi.setSystemTime(new Date(2026, 9, 14, 21, 45));
      let printed = '';
      vi.spyOn(print, 'printPaper').mockImplementation((paper) => {
        printed = paper.textContent ?? '';
      });
      m.answer(200, BROWSER);
      await click(m.find('cash-register-detail-print').element);
      expect(printed).toMatch(/9:45\s?PM/);
    } finally {
      vi.useRealTimers();
    }
  });

  it('a session that does not exist says so', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId(OP), 'cash_register.session_not_found'));
    await flush();
    expect(m.find('cash-register-detail-not-found').text()).toContain('That cash session does not exist.');
  });

  it('a failed read offers to retry', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId(OP), 'internal_error'));
    await flush();
    expect(m.find('cash-register-detail-error').text()).toContain('Could not load the session detail');
    expect(m.find('cash-register-detail-retry').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const m = await setup('es');
    await m.result(OP, SESSION);
    expect(m.find('cash-register-detail-title').text()).toBe('Detalle de la sesión · S-261014-0001');
    expect(m.find('cash-register-detail-print').text()).toContain('Imprimir');
  });
});
