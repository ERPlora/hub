// Kitchen → Display (WORKBOOK «Pantallas · Pantalla»; KITCHEN-F10 to F16): one bar with the three views
// and their counts («Tickets», «Ready», «All-Day»), «Full screen» when the device offers it and, with
// dishes of more than one station, the station buttons (remembered on this device). The cards of the
// view; a tap marks or recalls a dish, the card's buttons mark ready, rush, recall and serve, scoped to
// the station chosen. It rings for a new ticket or a rush (never for what was there when it opened). Empty,
// loading and error states with the old words.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { board, item, NOW, SETTINGS, ticket } from '../__tests__/kitchen';
import { click, EMPLOYEE, errorFrame, flush, type MountOptions, mountKitchen, VIEWER } from '../__tests__/mount-kitchen';
import DisplayPage from './DisplayPage.vue';

const BOARD = 'kitchen.ticket.board';
const ALL_DAY = 'kitchen.ticket.all_day';

function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => [...items.keys()][index] ?? null,
    removeItem: (key) => void items.delete(key),
    setItem: (key, value) => void items.set(key, String(value)),
  };
}

const play = vi.fn();
vi.mock('../lib/chime', () => ({
  Chime: class {
    play = play;
  },
}));

async function setup(options: MountOptions = {}) {
  const m = await mountKitchen(DisplayPage, { path: '/kitchen/display', ...options });
  await m.live();
  const show = async (data = board(), match: Record<string, unknown> = {}) => {
    await m.result('kitchen.settings.get', SETTINGS);
    await m.result(BOARD, data, match);
  };
  const segment = async (testid: string, value: string) => {
    m.find(testid).element.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true }));
    await flush();
  };
  /** The words inside an element (Ionic's segment hosts answer no textContent in happy-dom). */
  const words = (testid: string) => m.find(testid).element.innerHTML.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
  const cards = () => m.wrapper.findAll('[data-testid^="kitchen-card-"][aria-label]').map((c) => c.attributes('data-testid'));
  return { ...m, show, segment, cards, words };
}

describe('DisplayPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    vi.stubGlobal('localStorage', memoryStorage());
    play.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('says it is loading, then paints the tickets being cooked with the views and their counts', async () => {
    const s = await setup();
    expect(s.find('kitchen-display-loading').text()).toBe('Loading the display…');
    await s.show(board({ cooking: [ticket('t1'), ticket('t2', { label: 'Table 9' })], ready: [ticket('t3', { status: 'ready' })] }));
    expect(s.cards()).toEqual(['kitchen-card-t1', 'kitchen-card-t2']);
    expect(s.find('kitchen-display-count-tickets').text()).toBe('2');
    expect(s.find('kitchen-display-count-ready').text()).toBe('1');
    expect(s.words('kitchen-display-views')).toContain('All-Day');
  });

  it('shows the ready tickets and what is left to cook in their views', async () => {
    const s = await setup();
    await s.show(board({ ready: [ticket('t3', { status: 'ready' })] }));
    expect(s.find('kitchen-display-empty').text()).toContain('No tickets on the line.');
    await s.segment('kitchen-display-views', 'ready');
    expect(s.cards()).toEqual(['kitchen-card-t3']);
    await s.segment('kitchen-display-views', 'allday');
    await s.reopen();
    await s.result(ALL_DAY, { rows: [{ product_id: null, name: 'Burger', unit: 'ud', station_id: null, station_name: '', quantity: '3.000' }] });
    expect(s.find('kitchen-display-allday').text()).toContain('Burger');
    expect(s.find('kitchen-display-allday').text()).toContain('3');
  });

  it('follows what is left to cook only while «All-Day» is open', async () => {
    const s = await setup();
    await s.show(board());
    expect(s.params(ALL_DAY)).toEqual([]);
    await s.segment('kitchen-display-views', 'allday');
    await s.reopen();
    expect(s.params(ALL_DAY)).toEqual([{}]);
    await s.segment('kitchen-display-views', 'tickets');
    // The SDK lets a subscription go after its grace (2 s), then reopens the stream without it.
    await s.clock.advance(2000);
    await s.reopen();
    expect(s.params(ALL_DAY)).toEqual([]);
  });

  it('chooses a station, asks the server for it and remembers it on this device', async () => {
    const s = await setup();
    const stations = [
      { id: 'st-grill', name: 'Grill', color: '#E03131' },
      { id: null, name: '', color: '' },
    ];
    await s.show(board({ cooking: [ticket('t1')], stations }));
    expect(s.words('kitchen-display-stations')).toContain('Grill');
    expect(s.words('kitchen-display-stations')).toContain('No station');
    await s.segment('kitchen-display-stations', 'st-grill');
    await s.reopen();
    expect(s.params(BOARD)).toEqual([{ station: 'st-grill' }]);
    expect(localStorage.getItem('kitchen.display.station')).toBe('st-grill');
  });

  it('a tap and the card buttons go to the server, scoped to the station chosen', async () => {
    localStorage.setItem('kitchen.display.station', 'none');
    const s = await setup();
    const t = ticket('t1', { status: 'preparing', items: [item('i1'), item('i2', { status: 'ready' })] });
    await s.show(board({ cooking: [t], stations: [{ id: null, name: '', color: '' }] }), { station: 'none' });
    s.answer(200, t);
    await click(s.find('kitchen-line-i1').element);
    await click(s.find('kitchen-card-t1-bump').element);
    await click(s.find('kitchen-card-t1-rush').element);
    await click(s.find('kitchen-line-i2').element);
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/kitchen/items/bump', { ticket_id: 't1', item_ids: ['i1'], station: 'none' }],
      ['/api/kitchen/items/bump', { ticket_id: 't1', item_ids: [], station: 'none' }],
      ['/api/kitchen/tickets/set_rush', { ticket_id: 't1', rush: true }],
      ['/api/kitchen/items/recall', { ticket_id: 't1', item_ids: ['i2'], station: 'none' }],
    ]);
  });

  it('serves a ready ticket from the «Ready» view', async () => {
    const s = await setup();
    const t = ticket('t3', { status: 'ready', items: [item('i1', { status: 'ready' })] });
    await s.show(board({ ready: [t] }));
    await s.segment('kitchen-display-views', 'ready');
    s.answer(200, { ...t, status: 'served' });
    await click(s.find('kitchen-card-t3-served').element);
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/kitchen/tickets/serve', { ticket_id: 't3' }]]);
  });

  it('says why a step was refused, and when the pass or the rush notice did not print', async () => {
    const s = await setup();
    const t = ticket('t1');
    await s.show(board({ cooking: [t] }));
    s.answer(409, { error: { code: 'kitchen.invalid_transition', message: 'That kitchen ticket is no longer in the state this action requires.' } });
    await click(s.find('kitchen-card-t1-bump').element);
    expect(s.find('kitchen-display-action-error').text()).toContain('no longer in the state');
    s.answer(200, { ...t, status: 'ready', print_error: 'No printer' });
    await click(s.find('kitchen-card-t1-bump').element);
    expect(s.find('kitchen-display-pass-warning').text()).toContain('The pass could not be printed.');
    s.answer(200, { ...t, priority: 'rush', print_error: 'No printer' });
    await click(s.find('kitchen-card-t1-rush').element);
    expect(s.find('kitchen-display-rush-warning').text()).toContain('The urgent notice could not be printed.');
  });

  it('rings for a new ticket or a rush, never for what was there when it opened', async () => {
    const s = await setup();
    await s.show(board({ cooking: [ticket('t1')] }));
    expect(play).not.toHaveBeenCalled();
    await s.result(BOARD, board({ cooking: [ticket('t1'), ticket('t2')] }), {}, 2);
    expect(play).toHaveBeenCalledWith({ tone: 'chime', volume: 70 });
    await s.result(BOARD, board({ cooking: [ticket('t1', { priority: 'rush' }), ticket('t2')] }), {}, 3);
    expect(play).toHaveBeenCalledTimes(2);
  });

  it('stays quiet with the sound off', async () => {
    const s = await setup();
    await s.result('kitchen.settings.get', { ...SETTINGS, sound_enabled: false });
    await s.result(BOARD, board({ cooking: [ticket('t1')] }));
    await s.result(BOARD, board({ cooking: [ticket('t1'), ticket('t2')] }), {}, 2);
    expect(play).not.toHaveBeenCalled();
  });

  it('goes back to every station when the one this device remembers no longer exists', async () => {
    localStorage.setItem('kitchen.display.station', 'st-gone');
    const s = await setup();
    expect(s.params(BOARD)).toEqual([{ station: 'st-gone' }]);
    s.net.lastStream().push(errorFrame(s.subId(BOARD), 'kitchen.station_not_found'));
    await flush();
    await s.reopen();
    expect(s.params(BOARD)).toEqual([{}]);
    expect(localStorage.getItem('kitchen.display.station')).toBeNull();
  });

  it('says it could not load, with Retry', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(BOARD), 'boom'));
    await flush();
    expect(s.find('kitchen-display-error').text()).toContain('Could not load the kitchen display');
    expect(s.find('kitchen-display-retry').exists()).toBe(true);
    // kitchen#12: a full-size touch target (44 px) on the kitchen's screen, never the small button.
    expect((s.find('kitchen-display-retry').element as HTMLElement & { size?: string }).size).toBeUndefined();
  });

  it('is only to look at for whoever may not change tickets', async () => {
    const s = await setup({ session: VIEWER });
    await s.show(board({ cooking: [ticket('t1')] }));
    expect(s.find('kitchen-card-t1-foot').exists()).toBe(false);
    await click(s.find('kitchen-line-t1-1').element);
    expect(s.sent()).toEqual([]);
  });

  it('a cook gets the buttons', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(board({ cooking: [ticket('t1')] }));
    expect(s.find('kitchen-card-t1-bump').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(board());
    expect(s.words('kitchen-display-views')).toContain('Comandas');
    expect(s.words('kitchen-display-views')).toContain('Resumen');
    expect(s.find('kitchen-display-empty').text()).toContain('No hay comandas en marcha.');
  });
});
