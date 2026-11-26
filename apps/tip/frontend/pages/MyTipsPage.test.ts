// Tips → My tips (TIP-F14; WORKBOOK «Pantallas · Mis propinas»): an employee's own tips of today and of the week, from
// Monday, live (`tip.report.mine`), each as its figures in all, by card, in cash and other ways; nothing of managing the
// tips is offered. Every state: loading, none this week, a user with no record of the team, an error with Retry,
// reconnecting and the app off.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { BYE, errorFrame, flush, tabsOf } from '../../../../base/frontend/__tests__/mount-in-shell';
import { EMPLOYEE, MANAGER, mountTip, onTheTwentyFifth } from '../__tests__/mount-tip';
import TipFigures from '../components/TipFigures.vue';
import type { MineOut } from '../operations';
import MyTipsPage from './MyTipsPage.vue';

const OP = 'tip.report.mine';
const EMPLOYEE_WITH_MENU = withMenu('tip', EMPLOYEE);

const MINE: MineOut = {
  member_name: 'Bea Gil',
  today: '2026-11-25',
  week_from: '2026-11-23',
  day: { card: 300, cash: 200, other: 0, total: 500, count: 2 },
  week: { card: 900, cash: 200, other: 150, total: 1250, count: 5 },
};
const NONE = { card: 0, cash: 0, other: 0, total: 0, count: 0 };

onTheTwentyFifth();

async function setup(locale: 'en' | 'es' = 'en', session = EMPLOYEE_WITH_MENU) {
  const m = await mountTip(MyTipsPage, { path: '/tip/mine', locale, session });
  await m.live();
  const figures = () => m.wrapper.findAllComponents(TipFigures).map((row) => [row.props('testid'), row.props('figures')]);
  return { ...m, figures };
}

describe('MyTipsPage', () => {
  it('sits under «Tips», where an employee is offered only «My tips»', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Tips');
    expect(tabsOf(s.wrapper)).toEqual([['mine', 'My tips']]);
  });

  it('follows the caller’s own tips, each row loading until they arrive', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    expect(s.figures()).toEqual([
      ['tip-mine-day', undefined],
      ['tip-mine-week', undefined],
    ]);
  });

  it('paints today’s and this week’s, the week said from its Monday', async () => {
    const s = await setup();
    await s.result(OP, MINE);
    expect(s.figures()).toEqual([
      ['tip-mine-day', MINE.day],
      ['tip-mine-week', MINE.week],
    ]);
    expect(s.find('tip-mine-day-heading').text()).toBe('Today');
    expect(s.find('tip-mine-week-heading').text()).toBe(`This week, since ${new Date('2026-11-23').toLocaleDateString('en')}`);
  });

  it('offers nothing of managing the tips: no list, no report, no recording, adjusting, voiding nor export', async () => {
    const s = await setup();
    await s.result(OP, MINE);
    expect(s.wrapper.findAll('ion-button')).toHaveLength(0);
    expect(s.wrapper.find('[data-testid^="tip-list"]').exists()).toBe(false);
    expect(s.wrapper.find('[data-testid^="tip-report"]').exists()).toBe(false);
    const manager = await setup('en', MANAGER);
    await manager.result(OP, MINE);
    expect(manager.wrapper.findAll('ion-button')).toHaveLength(0);
  });

  it('with none today but some this week, paints both rows', async () => {
    const s = await setup();
    await s.result(OP, { ...MINE, day: NONE });
    expect(s.find('tip-mine-empty').exists()).toBe(false);
    expect(s.figures()).toEqual([
      ['tip-mine-day', NONE],
      ['tip-mine-week', MINE.week],
    ]);
  });

  it('with no tip this week says so in place of the figures', async () => {
    const s = await setup();
    await s.result(OP, { ...MINE, day: NONE, week: NONE });
    expect(s.find('tip-mine-empty').text()).toContain('You have no tips this week yet.');
    expect(s.figures()).toEqual([]);
  });

  it('a user with no record of the team is told to have it linked, with no Retry', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'tip.member_not_linked'));
    await flush();
    expect(s.find('tip-mine-unlinked').text()).toContain('msg tip.member_not_linked');
    expect(s.find('tip-mine-retry').exists()).toBe(false);
    expect(s.figures()).toEqual([]);
  });

  it('a read that fails says so with «Retry», which reads them again', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'tip.boom'));
    await flush();
    expect(s.find('tip-mine-error').text()).toContain('Your tips could not be loaded.');
    const streams = s.net.streams.length;
    await s.find('tip-mine-retry').trigger('click');
    await flush();
    expect(s.net.streams.length).toBeGreaterThan(streams);
  });

  it('while the stream reconnects keeps the figures and says «Reconnecting…»; the app off replaces them', async () => {
    const s = await setup();
    await s.result(OP, MINE);
    s.net.lastStream().push(BYE);
    await flush();
    expect(s.find('tip-mine-reconnecting').text()).toBe('Reconnecting…');
    expect(s.figures()).toHaveLength(2);
    const off = await setup();
    off.net.lastStream().push(errorFrame(off.subId(OP), 'app_inactive'));
    await flush();
    expect(off.find('tip-mine-inactive').exists()).toBe(true);
    expect(off.figures()).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result(OP, MINE);
    expect(tabsOf(s.wrapper)).toEqual([['mine', 'My tips']]);
    expect(s.find('tip-mine-day-heading').text()).toBe('Hoy');
    expect(s.find('tip-mine-week-heading').text()).toBe(`Esta semana, desde el ${new Date('2026-11-23').toLocaleDateString('es')}`);
  });
});
