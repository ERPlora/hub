// The notices above a kitchen list (WORKBOOK «Estados de cada pantalla»): «Reconnecting…» while the
// stream recovers (what is painted stays); and, instead of the list, «This app is not active in this
// business» or «You do not have permission» when the server says so. Any other failure is the table's
// own error state, with «Retry».
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { mountKitchen } from '../__tests__/mount-kitchen';
import PageNotices, { blockingError } from './PageNotices.vue';

const live = (code: string) => new ApiError(0, code, `msg ${code}`);

async function setup(props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(PageNotices, { props: { status: 'live', error: null, testid: 'kitchen-tickets', ...props }, locale });
  const banners = () =>
    m.wrapper.findAllComponents(InlineFeedback).map((b) => [b.attributes('data-testid'), b.props('tone'), b.props('heading') ?? null, b.text()]);
  return { ...m, banners };
}

describe('PageNotices', () => {
  it('says nothing while the list is live', async () => {
    expect((await setup({})).banners()).toEqual([]);
  });

  it('shows «Reconnecting…» while the stream recovers', async () => {
    expect((await setup({ status: 'reconnecting' })).banners()).toEqual([['kitchen-tickets-reconnecting', 'warning', null, 'Reconnecting… What you see may be out of date.']]);
  });

  it('says the app is not active, or that there is no permission, with the server’s words', async () => {
    expect((await setup({ status: 'error', error: live('app_inactive') })).banners()).toEqual([
      ['kitchen-tickets-inactive', 'warning', 'Kitchen is not active in this business.', expect.stringContaining('msg app_inactive')],
    ]);
    expect((await setup({ status: 'error', error: live('permission_denied') })).banners()).toEqual([
      ['kitchen-tickets-forbidden', 'warning', 'You do not have permission to see this.', expect.stringContaining('msg permission_denied')],
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
    const s = await setup({ status: 'reconnecting' }, 'es');
    expect(s.banners().map(([, , , text]) => text)).toEqual(['Reconectando… Lo que ves puede no estar al día.']);
  });
});
