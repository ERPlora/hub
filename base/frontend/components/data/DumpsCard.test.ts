// Settings › Data › Reset › «Copies» (round 2026-10-30 of PLAN-DB, decision 2 and proposal (l)): the full copies of the
// business's data ERPlora keeps for 90 days (one before each reset), newest first, each with its date, why it was made
// and its size, and «Download», whose link (15 minutes) is asked on each click; what a copy is next to «Export». Its
// states: reading, could not be read (with «Retry»), none yet; hidden while the business shares its database.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../../__tests__/mount-base';
import type { HubDumps } from '../../operations';
import DumpsCard from './DumpsCard.vue';

const data = vi.hoisted(() => ({ downloadFrom: vi.fn() }));
vi.mock('../../lib/data', async (original) => ({ ...(await original<typeof import('../../lib/data')>()), ...data }));

const DUMPS: HubDumps = {
  available: true,
  reset: null,
  dumps: [
    { id: 'd2', kind: 'offboarding', created_at: '2026-10-31T10:20:00Z', bytes: 1.5 * 1024 * 1024 },
    { id: 'd1', kind: 'reset', created_at: '2026-10-30T09:00:00Z', bytes: 2048 },
  ],
};

type Props = { dumps?: HubDumps; failed?: boolean };

async function card(props: Props, answer: (url: string) => Response = () => Response.json({ url: 'https://s3.example/d2?X-Amz-Expires=900', expires_at: '2026-10-31T10:35:00Z' }), locale: 'en' | 'es' = 'en') {
  const m = await mountBase(DumpsCard, { props, locale, onApi: ({ url }) => answer(url) });
  await flush();
  return m;
}

beforeEach(() => data.downloadFrom.mockReset());
afterEach(() => {
  document.body.innerHTML = '';
});

describe('DumpsCard', () => {
  it('lists the copies newest first with when, why and how big, and says what a copy is next to «Export»', async () => {
    const m = await card({ dumps: DUMPS });
    const rows = m.wrapper.findAll('[data-testid="dump-row"]');
    expect(rows.map((row) => row.attributes('data-id'))).toEqual(['d2', 'd1']);
    expect(rows[0].text()).toContain('When the business was deleted');
    expect(rows[0].text()).toContain('1.5 MB');
    expect(rows[1].text()).toContain('Before a reset');
    expect(rows[1].text()).toContain('2 KB');
    expect(rows[1].text()).toContain('Oct 30, 2026');
    const intro = m.wrapper.get('[data-testid="dumps-intro"]').text();
    expect(intro).toContain('keeps it for 90 days');
    expect(intro).toContain('pg_restore');
    expect(intro).toContain('«Export»');
  });

  it('asks for the link of a copy on each click and hands it to the browser', async () => {
    const m = await card({ dumps: DUMPS });
    await m.wrapper.get('[data-testid="dump-download-d2"]').trigger('click');
    await flush();
    await flush();
    expect(m.net.api.map((call) => call.url)).toEqual(['/api/settings/data/dumps/link?id=d2']);
    expect(data.downloadFrom).toHaveBeenCalledWith('https://s3.example/d2?X-Amz-Expires=900');
    await m.wrapper.get('[data-testid="dump-download-d2"]').trigger('click');
    await flush();
    await flush();
    expect(m.net.api).toHaveLength(2);
  });

  it('a link that cannot be given says why next to the copy, and nothing is downloaded', async () => {
    const m = await card({ dumps: DUMPS }, () =>
      Response.json(
        { error: { code: 'base.dumps_unavailable', message: 'The copy cannot be downloaded right now. Try again in a moment.' } },
        { status: 503 },
      ),
    );
    await m.wrapper.get('[data-testid="dump-download-d1"]').trigger('click');
    await flush();
    await flush();
    expect(m.wrapper.get('[data-testid="dump-error-d1"]').text()).toContain('The copy cannot be downloaded right now.');
    expect(data.downloadFrom).not.toHaveBeenCalled();
  });

  it('says there is no copy yet', async () => {
    const m = await card({ dumps: { ...DUMPS, dumps: [] } });
    expect(m.wrapper.get('[data-testid="dumps-empty"]').text()).toBe('No copies yet: one is made before each reset.');
  });

  it('while reading says so, and when it could not read offers «Retry»', async () => {
    const reading = await card({});
    expect(reading.wrapper.get('[data-testid="dumps-loading"]').attributes('aria-busy')).toBe('true');
    const failed = await card({ failed: true });
    expect(failed.wrapper.text()).toContain('The copies could not be read.');
    await failed.wrapper.get('[data-testid="dumps-retry"]').trigger('click');
    expect(failed.wrapper.emitted('retry')).toHaveLength(1);
  });

  it('is not shown while the business shares its database (it never gets a copy)', async () => {
    const m = await card({ dumps: { available: false, reset: null, dumps: [] } });
    expect(m.wrapper.find('[data-testid="dumps-card"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const m = await card({ dumps: DUMPS }, undefined, 'es');
    expect(m.wrapper.get('[data-testid="dumps-card"]').text()).toContain('Copias de los datos');
    expect(m.wrapper.findAll('[data-testid="dump-row"]')[1].text()).toContain('Antes de restablecer');
    expect(m.wrapper.get('[data-testid="dump-download-d1"]').text()).toBe('Descargar');
  });
});
