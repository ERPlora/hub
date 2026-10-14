// The notices above a back-office list of the sale app (WORKBOOK «Estados de cada pantalla»): «Reconnecting…»
// while the stream recovers (what is painted stays), «This app is not active in this business.» or «You do
// not have permission.» in place of the list, and a refused row action (a delete) with its heading and the
// server's words.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { mountSale } from '../../__tests__/mount-sale';
import ListNotices, { blockingError } from './ListNotices.vue';

async function setup(props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(ListNotices, { props: { status: 'live', error: null, testid: 'list', ...props }, locale });
  return m;
}

describe('blockingError', () => {
  it('the app off here or a person who may not look replace the list; any other failure is the table’s', () => {
    expect(blockingError(new ApiError(0, 'app_inactive', 'off'))).toBe('app_inactive');
    expect(blockingError(new ApiError(0, 'permission_denied', 'no'))).toBe('permission_denied');
    expect(blockingError(new ApiError(0, 'server_error', 'boom'))).toBeNull();
    expect(blockingError(null)).toBeNull();
  });
});

describe('ListNotices', () => {
  it('says nothing while all is well', async () => {
    const m = await setup({});
    expect(m.wrapper.text()).toBe('');
  });

  it('«Reconnecting…» while the stream recovers', async () => {
    const m = await setup({ status: 'reconnecting' });
    expect(m.find('list-reconnecting').text()).toBe('Reconnecting…');
  });

  it('the app off: «This app is not active in this business.» with the server’s words', async () => {
    const m = await setup({ status: 'error', error: new ApiError(0, 'app_inactive', 'Sales & POS is off.') });
    expect(m.find('list-inactive').text()).toContain('This app is not active in this business.');
    expect(m.find('list-inactive').text()).toContain('Sales & POS is off.');
  });

  it('no permission to look: «You do not have permission.»', async () => {
    const m = await setup({ status: 'error', error: new ApiError(0, 'permission_denied', 'Ask a manager.') }, 'es');
    expect(m.find('list-forbidden').text()).toContain('No tienes permiso.');
  });

  it('a refused row action: its heading and the server’s words', async () => {
    const m = await setup({ refused: { heading: 'The quick note could not be deleted.', message: 'It is gone.' } });
    const notice = m.find('list-error');
    expect(notice.text()).toContain('The quick note could not be deleted.');
    expect(notice.text()).toContain('It is gone.');
  });
});
