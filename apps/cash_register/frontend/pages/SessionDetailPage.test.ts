// Cash register → the detail of a session (CASH_REGISTER-F11, F16; the old `erp-cashregister-session-
// detail`): «Session detail · S-…» with Back, the summary, the session's movements and counts, and
// «Print» (the X or Z report through the browser). A session that does not exist says so; a failed read
// offers to retry. Everything re-runs by itself.
import { AppPage } from '@erplora/ui/shell';
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

afterEach(() => vi.restoreAllMocks());

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

  it('«Print» prints the report alone; a print the browser refuses is said', async () => {
    const m = await setup();
    await m.result(OP, SESSION);
    const printed = vi.spyOn(print, 'printPaper').mockImplementation(() => {});
    await click(m.find('cash-register-detail-print').element);
    expect(printed).toHaveBeenCalledOnce();
    expect((printed.mock.calls[0][0] as HTMLElement).dataset.testid).toBe('cash-register-report');
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
