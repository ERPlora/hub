// System › Failed events (BASE-G91…G94; the old hub's SystemPage `#events`, HUB_SHELL-F145…F148): the live
// `base.failed_event.list` — each event the relay gave up on with where it went, its attempts and its last error —,
// «Resend» and «Discard» with their labels (the old icons had none), «Resend all» confirmed first, discarding in the
// product's own dialog with an optional reason, and a failed read that is never «All in order» and keeps «Retry» in
// sight (hub#2540). The reasons of a failure come from the error's code.
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { FailedEvent } from '../operations';
import FailedEvents from './FailedEvents.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'base.failed_event.list';

function failed(id: string, over: Partial<FailedEvent> = {}): FailedEvent {
  return {
    id,
    event_id: `e-${id}`,
    name: 'sale.sale.completed',
    source_app: 'sale',
    source_app_name: 'Sales & POS',
    target_app: 'invoice',
    target_app_name: 'Invoicing',
    attempts: 8,
    occurred_at: '2026-10-23T18:50:00Z',
    last_error: 'Conflict: Set up the issuer first.',
    retryable: true,
    ...over,
  };
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(FailedEvents, options);
  const call = await m.live();
  return { ...m, call };
}

function inDoc(testid: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-testid="${testid}"]`);
  if (!element) throw new Error(`no ${testid} in the document`);
  return element;
}

const posted = (m: Awaited<ReturnType<typeof open>>) =>
  m.net.api.map((c) => [c.url, JSON.parse(String(c.init.body ?? '{}')) as Record<string, unknown>]);

beforeEach(() => {
  mocks.confirm.mockReset();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('FailedEvents', () => {
  it('follows the 100 most recent failed events live, loading meanwhile', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{ limit: 100 }]);
    expect(m.wrapper.find('[data-testid="failed-events-loading"]').exists()).toBe(true);
  });

  it('with none: «All in order», and no «Resend all»', async () => {
    const m = await open();
    await m.result(m.call, OP, { items: [], total: 0 });
    expect(m.wrapper.find('[data-testid="failed-events-empty"]').text()).toContain('All in order');
    expect(m.wrapper.text()).toContain('a restart never loses it');
    expect(m.wrapper.find('[data-testid="failed-events-retry-all"]').exists()).toBe(false);
  });

  it('each one says the event, where it went, its attempts and its last error, with labelled actions', async () => {
    const m = await open();
    await m.result(m.call, OP, { items: [failed('d1')], total: 1 });
    const row = m.wrapper.find('[data-testid="failed-event-row"]');
    expect(row.find('code').text()).toBe('sale.sale.completed');
    expect(row.text()).toContain('From Sales & POS to Invoicing');
    expect(row.text()).toContain('Attempts: 8');
    expect(row.text()).toContain('Conflict: Set up the issuer first.');
    expect(row.find('[data-testid="failed-event-retry"]').text()).toBe('Resend');
    expect(row.find('[data-testid="failed-event-discard"]').text()).toBe('Discard');
    expect(m.wrapper.text()).toContain('Fix the cause');
  });

  it('one that cannot be resent says why and has no «Resend», but can be discarded', async () => {
    const m = await open();
    await m.result(m.call, OP, { items: [failed('d1', { retryable: false })], total: 1 });
    const row = m.wrapper.find('[data-testid="failed-event-row"]');
    expect(row.find('[data-testid="failed-event-not-retryable"]').text()).toContain(
      'Invoicing is no longer on in this business',
    );
    expect(row.find('[data-testid="failed-event-retry"]').exists()).toBe(false);
    expect(row.find('[data-testid="failed-event-discard"]').exists()).toBe(true);
  });

  it('says when there are more than it shows', async () => {
    const m = await open();
    await m.result(m.call, OP, { items: [failed('d1'), failed('d2')], total: 130 });
    expect(m.wrapper.find('[data-testid="failed-events-more"]').text()).toBe('Showing the 2 most recent of 130.');
  });

  it('resends one: its button waits while it goes, then says so', async () => {
    let answer!: (response: Response) => void;
    const m = await open({ onApi: () => new Promise<Response>((resolve) => (answer = resolve)) });
    await m.result(m.call, OP, { items: [failed('d1'), failed('d2')], total: 2 });

    await m.wrapper.findAll('[data-testid="failed-event-retry"]')[0]!.trigger('click');
    await flush();

    expect(posted(m)).toEqual([['/api/system/failed-events/retry', { id: 'd1' }]]);
    const disabled = m.wrapper
      .findAll('[data-testid="failed-event-retry"]')
      .map((button) => (button.element as HTMLElement & { disabled?: boolean }).disabled);
    expect(disabled).toEqual([true, false]);
    answer(Response.json({ id: 'd1' }));
    await flush();
    expect(toastSuccess).toHaveBeenCalledWith('Event resent.');
  });

  it('a resend refused says why from its code, never from the text of the Hub', async () => {
    const m = await open({
      onApi: () => Response.json({ error: { code: 'not_found', message: 'Gone (server words)' } }, { status: 404 }),
    });
    await m.result(m.call, OP, { items: [failed('d1')], total: 1 });

    await m.wrapper.find('[data-testid="failed-event-retry"]').trigger('click');
    await flush();

    expect(toastError).toHaveBeenCalledWith('Could not resend: that event is no longer in the queue; refresh the list.');
  });

  it('«Resend all» asks first, then resends and says how many', async () => {
    const m = await open({ onApi: () => Response.json({ count: 3 }) });
    await m.result(m.call, OP, { items: [failed('d1'), failed('d2'), failed('d3')], total: 3 });

    mocks.confirm.mockResolvedValueOnce(false);
    await m.wrapper.find('[data-testid="failed-events-retry-all"]').trigger('click');
    await flush();
    expect(m.net.api).toEqual([]);

    mocks.confirm.mockResolvedValueOnce(true);
    await m.wrapper.find('[data-testid="failed-events-retry-all"]').trigger('click');
    await flush();
    expect(mocks.confirm).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: 'Resend every failed event?', confirmLabel: 'Resend all', tone: 'primary' }),
    );
    expect(posted(m)).toEqual([['/api/system/failed-events/retry_all', {}]]);
    expect(toastSuccess).toHaveBeenCalledWith('Events resent: 3.');
  });

  it('«Resend all» with nothing that could go says so', async () => {
    const m = await open({ onApi: () => Response.json({ count: 0 }) });
    await m.result(m.call, OP, { items: [failed('d1', { retryable: false })], total: 1 });
    mocks.confirm.mockResolvedValueOnce(true);

    await m.wrapper.find('[data-testid="failed-events-retry-all"]').trigger('click');
    await flush();

    expect(toastSuccess).toHaveBeenCalledWith('There was nothing to resend.');
  });

  it('discards in the product’s dialog, with what is lost and an optional reason', async () => {
    const m = await open({ onApi: () => Response.json({ id: 'd1' }) });
    await m.result(m.call, OP, { items: [failed('d1')], total: 1 });

    await m.wrapper.find('[data-testid="failed-event-discard"]').trigger('click');
    await flush();
    const dialog = inDoc('failed-event-discard-dialog');
    expect(dialog.textContent).toContain('Discard this event for good?');
    expect(dialog.textContent).toContain('“sale.sale.completed” will never reach Invoicing again.');
    expect(dialog.textContent).toContain('that sale stays without its invoice');
    inDoc('failed-event-discard-reason').dispatchEvent(
      new CustomEvent('ionInput', { detail: { value: 'Invoiced by hand.' } }),
    );
    await flush();
    inDoc('failed-event-discard-dialog-submit').click();
    await flush();

    expect(posted(m)).toEqual([['/api/system/failed-events/discard', { id: 'd1', reason: 'Invoiced by hand.' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Event discarded (kept for the audit).');
  });

  it('a failed read is never «All in order»: it says so and keeps «Retry» in sight (hub#2540)', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    const error = m.wrapper.find('[data-testid="failed-events-error"]');
    expect(error.text()).toContain('The queue of failed events could not be loaded.');
    expect(m.wrapper.find('[data-testid="failed-events-empty"]').exists()).toBe(false);
    const retry = m.wrapper.find('[data-testid="failed-events-reload"]');
    expect(retry.isVisible()).toBe(true);
    const before = m.net.opened.length;
    await retry.trigger('click');
    await flush();
    await m.clock.advance(200);
    await flush();
    expect(m.net.opened.length).toBeGreaterThan(before);
  });

  it('speaks Spanish', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, OP, { items: [failed('d1')], total: 1 });
    expect(m.wrapper.find('[data-testid="failed-event-retry"]').text()).toBe('Reenviar');
    expect(m.wrapper.find('[data-testid="failed-event-row"]').text()).toContain('De Sales & POS para Invoicing');
    expect(m.wrapper.find('[data-testid="failed-events-retry-all"]').text()).toBe('Reenviar todos');
  });
});
