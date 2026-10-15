// Time clock → Clock in (WORKBOOK «Pantallas · Fichar»; ATTENDANCE-F01, F02, F03): «Hello, <name>» and «It
// is <time>», the state of the day, the running time since the clock-in, the one button of the moment
// (Clock in, or Start/End break and Clock out), «Today» (Worked and Breaks, running) and «Recent days».
// Everything comes live (`attendance.record.current`, `attendance.settings.get`); a command answers with
// the server's time («Clocked in at 09:00.») or the server's refusal, and the screen follows the stream.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, click, errorFrame, flush, mountAttendance } from '../__tests__/mount-attendance';
import type { CurrentOut, RecordOut, SettingsOut } from '../operations';
import ClockPage from './ClockPage.vue';

const geo = vi.hoisted(() => ({ getPosition: vi.fn() }));
const device = vi.hoisted(() => ({ mode: 'shared' as 'shared' | 'personal' }));

vi.mock('../lib/geo', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/geo')>()),
  getPosition: geo.getPosition,
}));
vi.mock('../lib/device', () => ({ deviceMode: () => device.mode }));

const NOW = '2026-10-06T08:30:00Z'; // 10:30 in Madrid

function day(over: Partial<RecordOut> = {}): RecordOut {
  return {
    id: 'r1',
    member_id: 'm1',
    member_name: 'Ana López',
    work_date: '2026-10-06',
    clock_in_at: '2026-10-06T07:00:00Z',
    clock_out_at: null,
    status: 'open',
    source: 'shared',
    in_distance_m: null,
    in_within_radius: null,
    out_distance_m: null,
    out_within_radius: null,
    note: '',
    break_count: 0,
    break_seconds: 0,
    worked_seconds: 5400,
    break_started_at: null,
    correction_count: 0,
    as_of: NOW,
    ...over,
  };
}

function current(over: Partial<CurrentOut> = {}): CurrentOut {
  return {
    member: { id: 'm1', name: 'Ana López' },
    open: null,
    today: { date: '2026-10-06', worked_seconds: 0, break_seconds: 0, running: null },
    recent: [],
    as_of: NOW,
    ...over,
  };
}

const SETTINGS: SettingsOut = {
  require_location: false,
  geofence_radius_m: 100,
  workplace_lat: null,
  workplace_lng: null,
  auto_close_after_hours: 12,
  workplace_set: false,
  saved: false,
  updated_at: null,
};

const OPEN = current({
  open: day(),
  today: { date: '2026-10-06', worked_seconds: 5400, break_seconds: 0, running: 'work' },
  recent: [day(), day({ id: 'r0', work_date: '2026-10-05', clock_in_at: '2026-10-05T07:00:00Z', clock_out_at: '2026-10-05T15:00:00Z', status: 'closed', worked_seconds: 27000 })],
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
  vi.setSystemTime(new Date(NOW));
  device.mode = 'shared';
  geo.getPosition.mockReset();
});
afterEach(() => vi.useRealTimers());

async function setup(data: CurrentOut | null = current(), settings: SettingsOut = SETTINGS, locale: 'en' | 'es' = 'en') {
  const m = await mountAttendance(ClockPage, { session: EMPLOYEE, locale, path: '/attendance/clock' });
  await m.live();
  if (data) {
    await m.result('attendance.record.current', data);
    await m.result('attendance.settings.get', settings);
  }
  const text = (id: string) => m.find(id).exists() ? m.find(id).text() : null;
  const has = (id: string) => m.find(id).exists();
  return { ...m, text, has };
}

describe('ClockPage (ATTENDANCE-F01, F02)', () => {
  it('says it is loading until the day arrives', async () => {
    const s = await setup(null);
    expect(s.text('attendance-clock-loading')).toContain('Loading…');
  });

  it('greets by the staff record’s name, tells the time and offers «Clock in»', async () => {
    const s = await setup();
    expect(s.text('attendance-clock-greeting')).toBe('Hello, Ana López');
    expect(s.text('attendance-clock-now')).toBe('It is 10:30');
    expect(s.text('attendance-clock-status')).toBe('You are clocked out');
    expect(s.text('attendance-clock-in')).toContain('Clock in');
    expect([s.has('attendance-clock-out'), s.has('attendance-break-start'), s.has('attendance-clock-timer')]).toEqual([false, false, false]);
    expect(s.text('attendance-clock-empty')).toBe('No working days yet');
  });

  it('without a linked staff record it says so instead of a button', async () => {
    const s = await setup(current({ member: null }));
    expect(s.text('attendance-clock-unlinked')).toContain('Your user is not linked to any staff record');
    expect(s.has('attendance-clock-in')).toBe(false);
  });

  it('an open day: since when, the running time and today’s worked time tick by themselves', async () => {
    const s = await setup(OPEN);
    expect(s.text('attendance-clock-status')).toBe('Clocked in since 09:00');
    expect(s.text('attendance-clock-timer')).toBe('1:30:00');
    expect(s.text('attendance-clock-today-worked')).toContain('1:30');
    vi.advanceTimersByTime(61_000);
    await flush();
    expect(s.text('attendance-clock-timer')).toBe('1:31:01');
    expect(s.text('attendance-clock-now')).toBe('It is 10:31');
    expect(s.text('attendance-clock-today-worked')).toContain('1:31');
    expect([s.has('attendance-break-start'), s.has('attendance-clock-out'), s.has('attendance-clock-in')]).toEqual([true, true, false]);
  });

  it('lists the recent days with their times, worked time and status', async () => {
    const s = await setup(OPEN);
    const rows = s.wrapper.findAll('[data-testid="attendance-clock-recent-row"]').map((row) => row.text());
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain('09:00 – …');
    expect(rows[0]).toContain('In progress');
    expect(rows[1]).toContain('09:00 – 17:00');
    expect(rows[1]).toContain('7:30');
    expect(rows[1]).toContain('Closed');
  });

  it('on a break: since when, «End break», and the breaks of today run', async () => {
    const s = await setup(
      current({
        open: day({ break_started_at: '2026-10-06T08:00:00Z', break_count: 1, break_seconds: 1800 }),
        today: { date: '2026-10-06', worked_seconds: 3600, break_seconds: 1800, running: 'break' },
      }),
    );
    expect(s.text('attendance-clock-status')).toBe('On break since 10:00');
    expect(s.has('attendance-break-end')).toBe(true);
    vi.advanceTimersByTime(60_000);
    await flush();
    expect(s.text('attendance-clock-today-breaks')).toContain('0:31');
    expect(s.text('attendance-clock-today-worked')).toContain('1:00');
  });

  it('«Clock in» sends nothing the server does not need and answers with the server’s time', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/clock_in': [200, day()] });
    await click(s.find('attendance-clock-in').element);
    await flush();
    // The device mode is the server's to know (review of 2026-10-15, finding 6): never in the payload.
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/attendance/clock_in', query: {}, body: {} }]);
    expect(s.text('attendance-clock-message')).toBe('Clocked in at 09:00.');
  });

  it('a refusal says the server’s words', async () => {
    const s = await setup();
    s.answerBy({
      '/api/attendance/clock_in': [409, { error: { code: 'attendance.already_clocked_in', message: 'You already have an open working day.' } }],
    });
    await click(s.find('attendance-clock-in').element);
    await flush();
    expect(s.text('attendance-clock-message')).toBe('You already have an open working day.');
    expect(s.find('attendance-clock-message').attributes('role')).toBe('alert');
  });

  it('starts and ends a break, and clocks out', async () => {
    const s = await setup(OPEN);
    s.answerBy({
      '/api/attendance/breaks/start': [200, day({ break_started_at: '2026-10-06T08:30:00Z' })],
      '/api/attendance/clock_out': [200, day({ clock_out_at: '2026-10-06T15:00:00Z', status: 'closed' })],
    });
    await click(s.find('attendance-break-start').element);
    await flush();
    expect(s.text('attendance-clock-message')).toBe('Break started at 10:30.');
    await click(s.find('attendance-clock-out').element);
    await flush();
    expect(s.text('attendance-clock-message')).toBe('Clocked out at 17:00.');
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([
      ['/api/attendance/breaks/start', {}],
      ['/api/attendance/clock_out', {}],
    ]);
  });

  it('shows what the server answered at once, before the stream brings the new state (no double tap)', async () => {
    const s = await setup(
      current({
        open: day({ break_started_at: '2026-10-06T08:00:00Z', break_count: 1 }),
        today: { date: '2026-10-06', worked_seconds: 3600, break_seconds: 1800, running: 'break' },
      }),
    );
    s.answerBy({ '/api/attendance/breaks/end': [200, day({ break_started_at: null, break_count: 1, break_seconds: 1800 })] });
    await click(s.find('attendance-break-end').element);
    await flush();
    // The stream has not spoken yet: the answer of the command already rules the buttons.
    expect(s.text('attendance-clock-status')).toBe('Clocked in since 09:00');
    expect([s.has('attendance-break-end'), s.has('attendance-break-start')]).toEqual([false, true]);
    // The stream's next result takes over again.
    await s.result('attendance.record.current', current(), {}, 2);
    expect(s.text('attendance-clock-status')).toBe('You are clocked out');
  });

  it('runs on the server’s clock, not the device’s (review of 2026-10-15, finding 8)', async () => {
    // The device is ten minutes behind the server.
    vi.setSystemTime(new Date('2026-10-06T08:20:00Z'));
    const s = await setup(OPEN);
    expect(s.text('attendance-clock-now')).toBe('It is 10:30');
    expect(s.text('attendance-clock-timer')).toBe('1:30:00');
    expect(s.text('attendance-clock-today-worked')).toContain('1:30');
    vi.advanceTimersByTime(60_000);
    await flush();
    expect(s.text('attendance-clock-timer')).toBe('1:31:00');
  });

  it('a second tap while the first one is on its way sends nothing (review of 2026-10-15, finding 9)', async () => {
    const s = await setup();
    let answer!: (response: Response) => void;
    s.net.onApi(() => new Promise<Response>((resolve) => (answer = resolve)));
    const button = s.find('attendance-clock-in').element;
    await click(button);
    await click(button);
    await flush();
    expect(s.sent()).toHaveLength(1);
    // Vue sets `disabled` as the ion-button's property, not as an attribute.
    expect((s.find('attendance-clock-in').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    answer(Response.json(day()));
    await flush();
    expect(s.sent()).toHaveLength(1);
    expect(s.text('attendance-clock-message')).toBe('Clocked in at 09:00.');
  });

  it('a stream failure takes the screen with «Retry»', async () => {
    const s = await setup(null);
    s.net.lastStream().push(errorFrame(s.subId('attendance.record.current'), 'boom'));
    await flush();
    expect(s.text('attendance-clock-error')).toContain('The time clock could not be loaded');
    expect(s.has('attendance-clock-retry')).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup(OPEN, SETTINGS, 'es');
    expect(s.text('attendance-clock-greeting')).toBe('Hola, Ana López');
    expect(s.text('attendance-clock-status')).toBe('Dentro desde las 09:00');
    expect(s.text('attendance-clock-out')).toContain('Fichar salida');
  });
});

describe('ClockPage from a personal device when the business asks for the location (ATTENDANCE-F03)', () => {
  const REQUIRED: SettingsOut = { ...SETTINGS, require_location: true, workplace_lat: 40.4168, workplace_lng: -3.7038, workplace_set: true };

  it('reads the position and sends it; the Hub measures the distance', async () => {
    device.mode = 'personal';
    geo.getPosition.mockResolvedValue({ lat: 40.4173, lng: -3.7038, accuracy_m: 9.5 });
    const s = await setup(current(), REQUIRED);
    expect(s.text('attendance-clock-location-note')).toContain('Your location is checked');
    s.answerBy({ '/api/attendance/clock_in': [200, day({ source: 'personal', in_distance_m: 55.5, in_within_radius: true })] });
    await click(s.find('attendance-clock-in').element);
    await flush();
    expect(s.sent()[0].body).toEqual({ lat: 40.4173, lng: -3.7038, accuracy_m: 9.5 });
    expect(s.text('attendance-clock-distance')).toBe('You are 56 m from the workplace.');
  });

  it('a denied permission says so and sends nothing', async () => {
    device.mode = 'personal';
    const { GeoError } = await import('../lib/geo');
    geo.getPosition.mockRejectedValue(new GeoError('denied'));
    const s = await setup(current(), REQUIRED);
    await click(s.find('attendance-clock-in').element);
    await flush();
    expect(s.text('attendance-clock-message')).toContain('Location access is denied');
    expect(s.sent()).toEqual([]);
  });

  it('without the workplace set it says so before asking for the position', async () => {
    device.mode = 'personal';
    const s = await setup(current(), { ...REQUIRED, workplace_lat: null, workplace_lng: null, workplace_set: false });
    await click(s.find('attendance-clock-in').element);
    await flush();
    expect(s.text('attendance-clock-message')).toContain('The workplace location is not set yet');
    expect(geo.getPosition).not.toHaveBeenCalled();
    expect(s.sent()).toEqual([]);
  });

  it('clocking out never waits for a position that does not come', async () => {
    device.mode = 'personal';
    const { GeoError } = await import('../lib/geo');
    geo.getPosition.mockRejectedValue(new GeoError('timeout'));
    const s = await setup(OPEN, REQUIRED);
    s.answerBy({ '/api/attendance/clock_out': [200, day({ clock_out_at: '2026-10-06T15:00:00Z', status: 'closed' })] });
    await click(s.find('attendance-clock-out').element);
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/attendance/clock_out', query: {}, body: {} }]);
  });

  it('the counter POS is never asked, whatever the settings', async () => {
    const s = await setup(current(), REQUIRED);
    expect(s.has('attendance-clock-location-note')).toBe(false);
    s.answerBy({ '/api/attendance/clock_in': [200, day()] });
    await click(s.find('attendance-clock-in').element);
    await flush();
    expect(geo.getPosition).not.toHaveBeenCalled();
    expect(s.sent()[0].body).toEqual({});
  });
});
