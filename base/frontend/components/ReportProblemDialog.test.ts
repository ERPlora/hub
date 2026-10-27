// BASE-F108 · «Report a problem» without leaving the hub: the user menu opens the dialog of `@erplora/ui`
// (ReportProblemModal), which sends `base.support.report` with the screen the person is on; erplora.com answers the
// address support writes back to. A refusal (the limit, erplora.com out of reach) is said in it, and what was typed
// stays.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import { openReportProblem, reportProblemOpen } from '../lib/report-problem';
import ReportProblemDialog from './ReportProblemDialog.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  reportProblemOpen.value = false;
  document.body.innerHTML = '';
});

type Field = HTMLElement & { value?: string };
const find = (testid: string) => document.querySelector<HTMLElement>(`[data-testid="${testid}"]`);
const get = (testid: string): HTMLElement => {
  const el = find(testid);
  if (!el) throw new Error(`no [data-testid="${testid}"]`);
  return el;
};

async function type(testid: string, value: string): Promise<void> {
  const el = get(testid) as Field;
  el.value = value;
  el.dispatchEvent(new CustomEvent('ionInput', { detail: { value }, bubbles: true }));
  await flush();
}

async function dialog(answer: () => Response, locale: 'en' | 'es' = 'en') {
  const mounted = await mountBase(ReportProblemDialog, {
    path: '/sales/pos?table=4',
    routes: ['/sales/pos'],
    locale,
    onApi: answer,
  });
  const sent = () =>
    mounted.net.api.filter((call) => call.url.startsWith('/api/support/report')).map((call) => JSON.parse(String(call.init.body)));
  return { ...mounted, sent };
}

async function openAndFill(): Promise<void> {
  openReportProblem();
  await flush();
  await type('report-problem-subject', 'The printer stops');
  await type('report-problem-description', 'It prints half a ticket.');
}

async function send(): Promise<void> {
  get('report-problem-submit').dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await flush();
  await flush();
}

describe('ReportProblemDialog', () => {
  it('stays closed until the user menu asks, then opens «Report a problem»', async () => {
    await dialog(() => Response.json({ reply_to: 'ana@example.com' }));
    await flush();
    expect(find('report-problem-subject')).toBeNull();
    openReportProblem();
    await flush();
    expect(get('report-problem').getAttribute('aria-label')).toBe('Report a problem');
    expect(find('report-problem-subject')).not.toBeNull();
  });

  it('sends base.support.report with what was typed and the screen the person is on, and says where support answers', async () => {
    const { sent } = await dialog(() => Response.json({ reply_to: 'ana@example.com' }));
    await openAndFill();
    await send();
    expect(sent()).toEqual([{ subject: 'The printer stops', description: 'It prints half a ticket.', page: '/sales/pos?table=4' }]);
    expect(get('report-problem-sent').textContent).toContain(
      'Thank you: we have received your report and will reply to ana@example.com as soon as possible.',
    );
    get('report-problem-done').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flush();
    expect(reportProblemOpen.value).toBe(false);
  });

  it("erplora.com's refusal is said in the dialog and what was typed stays", async () => {
    await dialog(() =>
      Response.json(
        { error: { code: 'base.too_many_attempts', message: 'Too many attempts. Please try again in a few minutes.' } },
        { status: 429 },
      ),
    );
    await openAndFill();
    await send();
    expect(get('report-problem-error').textContent?.trim()).toBe('Too many attempts. Please try again in a few minutes.');
    expect((get('report-problem-subject') as Field).value).toBe('The printer stops');
    expect(find('report-problem-sent')).toBeNull();
  });

  it('speaks Spanish with a Spanish person', async () => {
    await dialog(() => Response.json({ reply_to: 'ana@example.com' }), 'es');
    openReportProblem();
    await flush();
    expect(get('report-problem').getAttribute('aria-label')).toBe('Reportar un problema');
  });
});
