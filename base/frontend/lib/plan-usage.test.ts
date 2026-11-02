// What System › «Usage and plan» says from the figures (BASE-F40): the one line at the top that tells whoever runs the
// business whether to upgrade, and its rows, the fullest first. Pure functions: the screen only paints them.
import { describe, expect, it } from 'vitest';

import type { AssistantUsage, PlanMeter, PlanUsage } from '../operations';
import { NEAR_PERCENT, usageRows, verdictOf } from './plan-usage';

const GB = 1024 ** 3;

const USAGE: PlanUsage = {
  known: true,
  demo: false,
  plan_slug: 'starter',
  people: { used: 1, limit: 5 },
  devices: { used: 1, limit: 3 },
  apps: { used: 2, limit: 10 },
  database: { available: true, bytes: 5 * 1024 * 1024, day: '2026-10-30' },
  files: { bytes: GB, day: '2026-10-30', limit: 5 * GB, percent: 20, status: 'within' },
  connections: { peak_today: 1, limit: 3, busy_last_7_days: 0, busy_since: null, bigger_plan_gives_more: true },
  requests: { this_month: 100, since: null },
  activity: { active_now: 1, last_30_days: 2, day: '2026-10-30' },
  meters: [],
};

const whatsapp = (used: number | null, limit: number | null, available = true): PlanMeter => ({
  key: 'whatsapp_inbox',
  label: 'WhatsApp',
  used,
  limit,
  available,
});
const assistant = (used: number, limit: number): AssistantUsage => ({ used, limit, resets_at: null, demo: false });
/** The assistant's messages read, with room: nothing left to check about them. */
const READ = assistant(10, 300);
const figures = (parts: Partial<PlanUsage>): PlanUsage => ({ ...USAGE, ...parts });
const filesAt = (percent: number, status: 'within' | 'near' | 'full') => ({ ...USAGE.files, percent, status });
const shortBy = (count: number, bigger = true) => ({ ...USAGE.connections, busy_last_7_days: count, bigger_plan_gives_more: bigger });

describe('verdictOf', () => {
  it('tells whoever has room that the plan is enough', () => {
    expect(verdictOf(USAGE, READ)).toEqual({ tone: 'success', motive: null, full: [], neutral: null });
  });

  it.each([
    ['full files', figures({ files: filesAt(100, 'full') }), null, 'files', 100],
    ['past the space', figures({ files: filesAt(130, 'full') }), null, 'files', 130],
    ['the assistant spent', USAGE, assistant(300, 300), 'assistant', 100],
    ['WhatsApp spent', figures({ meters: [whatsapp(150, 150)] }), null, 'whatsapp_inbox', 100],
    ['capacity that fell short when a bigger plan helps', figures({ connections: shortBy(1) }), null, 'capacity', 100],
  ] as const)('is red with %s', (_, usage, messages, key, fullness) => {
    const verdict = verdictOf(usage, messages);
    expect(verdict.tone).toBe('danger');
    expect(verdict.motive).toMatchObject({ key, fullness });
  });

  it.each([
    ['files at 80 %', figures({ files: filesAt(80, 'near') }), null, 'files', 80],
    ['the assistant at 80 %', USAGE, assistant(240, 300), 'assistant', 80],
    ['WhatsApp at 80 %', figures({ meters: [whatsapp(120, 150)] }), null, 'whatsapp_inbox', 80],
    ['WhatsApp at 99 %', figures({ meters: [whatsapp(149, 150)] }), null, 'whatsapp_inbox', (149 / 150) * 100],
  ] as const)('is amber with %s', (_, usage, messages, key, fullness) => {
    const verdict = verdictOf(usage, messages);
    expect(verdict.tone).toBe('warning');
    expect(verdict.motive).toMatchObject({ key, fullness });
  });

  it.each([
    ['files just below', figures({ files: filesAt(79, 'within') }), READ],
    ['the assistant just below', USAGE, assistant(239, 300)],
    ['WhatsApp just below', figures({ meters: [whatsapp(119, 150)] }), READ],
  ] as const)('stays green with %s 80 %%', (_, usage, messages) => {
    expect(verdictOf(usage, messages).tone).toBe('success');
  });

  it('near starts where the server says it does', () => {
    expect(NEAR_PERCENT).toBe(80);
  });

  it('the most serious motive wins, and among equals the fullest', () => {
    const redBeatsAFullerAmber = verdictOf(figures({ meters: [whatsapp(150, 150)], files: filesAt(99, 'near') }), assistant(299, 300));
    expect(redBeatsAFullerAmber.motive?.key).toBe('whatsapp_inbox');
    const fullestAmber = verdictOf(figures({ files: filesAt(85, 'near'), meters: [whatsapp(135, 150)] }), assistant(240, 300));
    expect(fullestAmber).toMatchObject({ tone: 'warning', motive: { key: 'whatsapp_inbox' } });
    const fullestRed = verdictOf(figures({ files: filesAt(130, 'full'), connections: shortBy(3) }), assistant(300, 300));
    expect(fullestRed).toMatchObject({ tone: 'danger', motive: { key: 'files' } });
  });

  it('capacity never goes by its percentage: with a limit of 1 the first operation is its 100 %', () => {
    const usage = figures({ connections: { ...USAGE.connections, peak_today: 1, limit: 1 } });
    expect(verdictOf(usage, READ).tone).toBe('success');
  });

  it('people, devices and apps at their limit never change the colour: they are told apart, under the green line', () => {
    const usage = figures({
      people: { used: 5, limit: 5 },
      devices: { used: 1, limit: 1 },
      apps: { used: 11, limit: 10 },
    });
    expect(verdictOf(usage, READ)).toEqual({ tone: 'success', motive: null, full: ['people', 'devices', 'apps'], neutral: null });
  });

  it('with no limit nothing is ever full', () => {
    const usage = figures({ people: { used: 5, limit: null }, devices: { used: 1, limit: null }, apps: { used: 3, limit: null } });
    expect(verdictOf(usage, READ).full).toEqual([]);
  });

  it('what the plan does not include is no motive', () => {
    expect(verdictOf(figures({ meters: [whatsapp(0, 0)] }), assistant(0, 0)).tone).toBe('success');
  });

  it('what was not measured yet is no motive and does not hold the green: a business on its first day is fine', () => {
    const usage = figures({
      meters: [whatsapp(null, null)],
      files: { bytes: null, day: null, limit: 5 * GB, percent: null, status: null },
      connections: { ...USAGE.connections, peak_today: null, busy_last_7_days: null },
    });
    expect(verdictOf(usage, READ)).toMatchObject({ tone: 'success', neutral: null });
  });
});

describe('verdictOf, when it could not read everything', () => {
  // Green only when everything that applies was read: 30 of 30 messages with the assistant down must not read «enough».
  it('with the assistant still answering and no motive: neutral, checking, never green', () => {
    expect(verdictOf(USAGE, null)).toEqual({ tone: 'neutral', motive: null, full: [], neutral: 'checking' });
  });

  it('with the assistant failed and no motive: neutral, not everything checked, never green', () => {
    expect(verdictOf(USAGE, 'failed')).toEqual({ tone: 'neutral', motive: null, full: [], neutral: 'incomplete' });
  });

  it('with an app that could not be read and no motive: neutral, not everything checked', () => {
    const usage = figures({ meters: [whatsapp(null, null, false)] });
    expect(verdictOf(usage, READ)).toEqual({ tone: 'neutral', motive: null, full: [], neutral: 'incomplete' });
  });

  it('checking wins over failed while something can still change it', () => {
    const usage = figures({ meters: [whatsapp(null, null, false)] });
    expect(verdictOf(usage, null).neutral).toBe('checking');
  });

  it.each([
    ['still answering', null],
    ['failed', 'failed'],
  ] as const)('a motive is still true with the assistant %s: it is said', (_, read) => {
    const red = verdictOf(figures({ files: filesAt(100, 'full') }), read);
    expect(red).toMatchObject({ tone: 'danger', motive: { key: 'files' }, neutral: null });
    const amber = verdictOf(figures({ meters: [whatsapp(120, 150)] }), read);
    expect(amber).toMatchObject({ tone: 'warning', motive: { key: 'whatsapp_inbox' }, neutral: null });
  });

  it('a motive is still true with an app that could not be read', () => {
    const usage = figures({ files: filesAt(85, 'near'), meters: [whatsapp(null, null, false)] });
    expect(verdictOf(usage, READ)).toMatchObject({ tone: 'warning', neutral: null });
  });

  it('what the plan does not include is nothing to check', () => {
    expect(verdictOf(USAGE, assistant(0, 0))).toMatchObject({ tone: 'success', neutral: null });
    expect(verdictOf(figures({ meters: [whatsapp(0, 0)] }), READ)).toMatchObject({ tone: 'success', neutral: null });
    expect(verdictOf(figures({ meters: [] }), READ)).toMatchObject({ tone: 'success', neutral: null });
  });

  it('people, devices and apps at their limit are still told apart, whatever the line says', () => {
    const usage = figures({ people: { used: 5, limit: 5 } });
    expect(verdictOf(usage, null).full).toEqual(['people']);
  });
});

describe('verdictOf, with all the capacity the service gives and still falling short', () => {
  // The one thing the screen answers must not contradict itself: no green over «fell short 4 times», and no red or upgrade
  // either, because a bigger plan would give no more.
  const top = (count: number) => figures({ connections: shortBy(count, false) });

  it('says it on a neutral line: no motive to upgrade, never green', () => {
    expect(verdictOf(top(4), READ)).toEqual({ tone: 'neutral', motive: null, full: [], neutral: 'capacity' });
  });

  it('never having fallen short, it is green', () => {
    expect(verdictOf(top(0), READ)).toEqual({ tone: 'success', motive: null, full: [], neutral: null });
  });

  it('never counted yet, it is green', () => {
    const usage = figures({ connections: { ...USAGE.connections, busy_last_7_days: null, bigger_plan_gives_more: false } });
    expect(verdictOf(usage, READ)).toEqual({ tone: 'success', motive: null, full: [], neutral: null });
  });

  it('a real motive wins: files or messages can still be solved by a bigger plan', () => {
    const near = verdictOf(figures({ connections: shortBy(4, false), files: filesAt(85, 'near') }), READ);
    expect(near).toMatchObject({ tone: 'warning', motive: { key: 'files' }, neutral: null });
    const spent = verdictOf(top(4), assistant(300, 300));
    expect(spent).toMatchObject({ tone: 'danger', motive: { key: 'assistant' }, neutral: null });
  });

  it('it says nothing about upgrading until everything was read: that could still be a motive', () => {
    expect(verdictOf(top(4), null)).toMatchObject({ tone: 'neutral', neutral: 'checking' });
    expect(verdictOf(top(4), 'failed')).toMatchObject({ tone: 'neutral', neutral: 'incomplete' });
    const appDown = figures({ connections: shortBy(4, false), meters: [whatsapp(null, null, false)] });
    expect(verdictOf(appDown, READ)).toMatchObject({ tone: 'neutral', neutral: 'incomplete' });
  });

  it('with a bigger plan that would help it is still the red motive', () => {
    expect(verdictOf(figures({ connections: shortBy(4, true) }), READ)).toMatchObject({ tone: 'danger', motive: { key: 'capacity' } });
  });
});

describe('usageRows', () => {
  const ids = (usage: PlanUsage, messages: AssistantUsage | null | 'failed' = assistant(10, 300)) =>
    usageRows(usage, messages).map((row) => row.id);

  it('goes from the fullest down, capacity last', () => {
    const usage = figures({
      files: filesAt(84, 'near'),
      apps: { used: 7, limit: 10 },
      people: { used: 3, limit: 5 },
      devices: { used: 1, limit: 3 },
      connections: { ...USAGE.connections, peak_today: 3, limit: 3 },
      meters: [whatsapp(40, 150)],
    });
    expect(ids(usage, assistant(120, 300))).toEqual(['files', 'apps', 'people', 'assistant', 'devices', 'whatsapp_inbox', 'capacity']);
  });

  it('capacity that fell short and would be helped by a bigger plan goes first', () => {
    expect(ids(figures({ connections: shortBy(4) }))[0]).toBe('capacity');
  });

  it('what has no bar goes after what has one, and capacity last', () => {
    const usage = figures({ people: { used: 3, limit: null }, meters: [whatsapp(0, 0)] });
    expect(ids(usage).slice(-3)).toEqual(['people', 'whatsapp_inbox', 'capacity']);
  });

  it('each row says how full, in the tone of the line at the top', () => {
    const rows = usageRows(
      figures({
        files: filesAt(85, 'near'),
        people: { used: 5, limit: 5 },
        connections: shortBy(2),
        meters: [whatsapp(150, 150)],
      }),
      assistant(10, 300),
    );
    const of = (id: string) => rows.find((row) => row.id === id);
    expect(of('files')).toMatchObject({ percent: 85, tone: 'warning', pill: 'near', state: 'measured' });
    expect(of('whatsapp_inbox')).toMatchObject({ percent: 100, tone: 'danger', pill: 'full', state: 'measured' });
    // At its limit, «Full», and still green: a Free business with its one device in use is fine.
    expect(of('people')).toMatchObject({ percent: 100, tone: 'success', pill: 'full', state: 'measured' });
    expect(of('assistant')).toMatchObject({ tone: 'success', pill: null, state: 'measured' });
    expect(of('capacity')).toMatchObject({ tone: 'danger', pill: null, state: 'measured' });
  });

  it('capacity at the top of a plan that cannot grow stays green', () => {
    const capacity = usageRows(figures({ connections: shortBy(2, false) }), null).find((row) => row.id === 'capacity');
    expect(capacity?.tone).toBe('success');
  });

  it('says what has no limit, what the plan does not include, what is unavailable and what was not measured', () => {
    const rows = usageRows(
      figures({
        people: { used: 3, limit: null },
        files: { bytes: null, day: null, limit: 5 * GB, percent: null, status: null },
        connections: { ...USAGE.connections, peak_today: null },
        meters: [whatsapp(0, 0)],
      }),
      'failed',
    );
    const state = (id: string) => rows.find((row) => row.id === id)?.state;
    expect(state('people')).toBe('noLimit');
    expect(state('files')).toBe('notMeasured');
    expect(state('capacity')).toBe('notMeasured');
    expect(state('whatsapp_inbox')).toBe('notIncluded');
    expect(state('assistant')).toBe('unavailable');
  });

  it('the assistant with 0 is what the plan does not include, and while it answers it says so', () => {
    const state = (messages: AssistantUsage | null) => usageRows(USAGE, messages).find((row) => row.id === 'assistant')?.state;
    expect(state(assistant(0, 0))).toBe('notIncluded');
    expect(state(null)).toBe('loading');
  });

  it('files with no limit have a figure and no bar', () => {
    const rows = usageRows(figures({ files: { ...USAGE.files, limit: null, percent: null, status: null } }), null);
    expect(rows.find((row) => row.id === 'files')).toMatchObject({ state: 'noLimit', used: GB, percent: null });
  });

  it('an app that could not be read is unavailable, and one not measured yet says so', () => {
    const rows = usageRows(figures({ meters: [whatsapp(null, null, false)] }), null);
    expect(rows.find((row) => row.id === 'whatsapp_inbox')?.state).toBe('unavailable');
    const waiting = usageRows(figures({ meters: [whatsapp(null, null)] }), null);
    expect(waiting.find((row) => row.id === 'whatsapp_inbox')?.state).toBe('notMeasured');
  });

  it('without the plan: what is in use, with no limit, bar, pill, assistant or apps’ messages', () => {
    const rows = usageRows(
      figures({
        known: false,
        plan_slug: null,
        people: { used: 3, limit: null },
        devices: { used: 1, limit: null },
        apps: { used: 2, limit: null },
        files: { ...USAGE.files, limit: null, percent: null, status: null },
        connections: { ...USAGE.connections, limit: null, bigger_plan_gives_more: false },
        meters: [whatsapp(1, 150)],
      }),
      assistant(1, 300),
    );
    expect(rows.map((row) => row.id)).toEqual(['files', 'apps', 'people', 'devices', 'capacity']);
    expect(rows.every((row) => row.percent === null && row.pill === null && row.state === 'plain')).toBe(true);
  });
});
