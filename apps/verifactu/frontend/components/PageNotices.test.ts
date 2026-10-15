// The notices above a VeriFactu screen (the WORKBOOK's states of each screen): «Reconnecting…» while the
// stream recovers (what is painted stays); a read-only notice for whoever can only look (the Issuer); and,
// instead of the screen, «This app is not active in this business» or «You do not have permission» when the
// server says so.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { mountVerifactu } from '../__tests__/mount-verifactu';
import PageNotices, { blockingError } from './PageNotices.vue';

const live = (code: string) => new ApiError(0, code, `msg ${code}`);

async function setup(props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  const m = await mountVerifactu(PageNotices, { props: { status: 'live', error: null, testid: 'verifactu-list', ...props }, locale });
  const banners = () =>
    m.wrapper.findAllComponents(InlineFeedback).map((b) => [b.attributes('data-testid'), b.props('tone'), b.props('heading') ?? null, b.text()]);
  return { ...m, banners };
}

describe('PageNotices', () => {
  it('says nothing while the screen is live', async () => {
    expect((await setup({})).banners()).toEqual([]);
  });

  it('tells whoever can only look that they cannot change anything, with a lock', async () => {
    const s = await setup({ readOnly: 'You can look but not change it.' });
    expect(s.banners()).toEqual([['verifactu-list-readonly', 'info', null, 'You can look but not change it.']]);
    expect(s.wrapper.findComponent(InlineFeedback).props('icon')).toBe('lock-closed-outline');
  });

  it('shows «Reconnecting…» while the stream recovers', async () => {
    expect((await setup({ status: 'reconnecting' })).banners()).toEqual([['verifactu-list-reconnecting', 'warning', null, 'Reconnecting…']]);
  });

  it('says the app is not active, or that there is no permission, with the server’s words', async () => {
    expect((await setup({ status: 'error', error: live('app_inactive'), readOnly: 'x' })).banners()).toEqual([
      ['verifactu-list-inactive', 'warning', 'This app is not active in this business', expect.stringContaining('msg app_inactive')],
    ]);
    expect((await setup({ status: 'error', error: live('permission_denied') })).banners()).toEqual([
      ['verifactu-list-forbidden', 'warning', 'You do not have permission', expect.stringContaining('msg permission_denied')],
    ]);
  });

  it('leaves any other failure to the screen (its error state with «Retry»)', async () => {
    expect((await setup({ status: 'error', error: live('boom') })).banners()).toEqual([]);
    expect([blockingError(live('app_inactive')), blockingError(live('permission_denied')), blockingError(live('boom')), blockingError(null)]).toEqual([
      'app_inactive',
      'permission_denied',
      null,
      null,
    ]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ status: 'reconnecting' }, 'es');
    expect(s.banners().map(([, , , text]) => text)).toEqual(['Reconectando…']);
  });
});
