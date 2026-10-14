// The notices above a tax list (TAX-F01, F03, F13; the WORKBOOK's states of each screen): «Reconnecting…» while the
// stream recovers (what is painted stays); the read-only notice for whoever can only look («You can
// view the tax rules but not change them.», as the old screens); and, instead of the list, «This app
// is not active in this business» or «You do not have permission» when the server says so.
import { ApiError } from '@erplora/ui/sdk';
import { InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { mountTax } from '../__tests__/mount-tax';
import PageNotices, { blockingError } from './PageNotices.vue';

const live = (code: string) => new ApiError(0, code, `msg ${code}`);

async function setup(props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  const m = await mountTax(PageNotices, { props: { status: 'live', error: null, readOnly: false, testid: 'tax-rules', ...props }, locale });
  const banners = () => m.wrapper.findAllComponents(InlineFeedback).map((b) => [b.attributes('data-testid'), b.props('tone'), b.props('heading') ?? null, b.text()]);
  return { ...m, banners };
}

describe('PageNotices', () => {
  it('says nothing while the list is live and can be managed', async () => {
    expect((await setup({})).banners()).toEqual([]);
  });

  it('tells whoever can only look that they cannot change anything, with a lock', async () => {
    const s = await setup({ readOnly: true });
    expect(s.banners()).toEqual([['tax-rules-readonly', 'info', null, 'You can view the tax rules but not change them.']]);
    expect(s.wrapper.findComponent(InlineFeedback).props('icon')).toBe('lock-closed-outline');
  });

  it('shows «Reconnecting…» while the stream recovers', async () => {
    const s = await setup({ status: 'reconnecting' });
    expect(s.banners()).toEqual([['tax-rules-reconnecting', 'warning', null, 'Reconnecting…']]);
  });

  it('says the app is not active, or that there is no permission, with the server’s words, and no read-only notice', async () => {
    // The banner's text is its heading and then the message.
    expect((await setup({ status: 'error', error: live('app_inactive'), readOnly: true })).banners()).toEqual([
      ['tax-rules-inactive', 'warning', 'This app is not active in this business', expect.stringContaining('msg app_inactive')],
    ]);
    expect((await setup({ status: 'error', error: live('permission_denied'), readOnly: true })).banners()).toEqual([
      ['tax-rules-forbidden', 'warning', 'You do not have permission', expect.stringContaining('msg permission_denied')],
    ]);
  });

  it('leaves any other failure to the table (its error state with «Retry»)', async () => {
    expect((await setup({ status: 'error', error: live('boom') })).banners()).toEqual([]);
    expect([blockingError(live('app_inactive')), blockingError(live('permission_denied')), blockingError(live('boom')), blockingError(null)]).toEqual([
      'app_inactive',
      'permission_denied',
      null,
      null,
    ]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ readOnly: true, status: 'reconnecting' }, 'es');
    expect(s.banners().map(([, , , text]) => text)).toEqual(['Reconectando…', 'Puedes consultar las reglas fiscales pero no modificarlas.']);
  });
});
