// System › «Usage and plan» (BASE-F40) in ERPlora's own business: it has no plan and never will, so the screen promises
// none. It says what the business uses, with nothing to measure it against and nothing to upgrade.
import { afterEach, describe, expect, it } from 'vitest';

import type { PlanUsage } from '../operations/usage';
import { flush, mountBase } from '../__tests__/mount-base';
import SystemUsage from './SystemUsage.vue';

const OP = 'base.plan.usage';
const OWN: PlanUsage = {
  known: false,
  demo: false,
  platform: true,
  plan_slug: null,
  people: { used: 3, limit: null },
  devices: { used: 1, limit: null },
  apps: { used: 2, limit: null },
  database: { bytes: 312 * 1024 * 1024, day: '2026-10-30' },
  files: { bytes: 2 * 1024 ** 3, day: '2026-10-30', limit: null, percent: null, status: null },
  // It has limits of its own in the engine; they are no plan's, so no bar measures against them.
  connections: { peak_today: 2, limit: 6, busy_last_7_days: 0, busy_since: null, bigger_plan_gives_more: false },
  requests: { this_month: 18420, since: null },
  activity: { active_now: 2, last_30_days: 6, day: '2026-10-30' },
  meters: [{ key: 'whatsapp_inbox', label: 'WhatsApp', used: null, limit: null, available: true }],
};

async function open(usage: PlanUsage, locale: 'en' | 'es' = 'en') {
  const asked: string[] = [];
  const m = await mountBase(SystemUsage, {
    locale,
    onApi: ({ url }) => {
      asked.push(url);
      return Response.json({});
    },
  });
  await m.result(await m.live(), OP, usage);
  await flush();
  return { ...m, asked, part: (id: string) => m.wrapper.find(`[data-testid="system-usage-${id}"]`) };
}

afterEach(() => {
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('SystemUsage in ERPlora’s own business', () => {
  it('says it has no plan, never that one will come', async () => {
    const m = await open(OWN);
    expect(m.part('platform').text()).toBe("This is ERPlora's own business: it has no plan.");
    expect(m.part('platform').attributes('data-tone')).toBe('info');
    expect(m.part('unknown').exists()).toBe(false);
    expect(m.wrapper.text()).not.toContain('erplora.com');
  });

  it('lo dice en español', async () => {
    const m = await open(OWN, 'es');
    expect(m.part('platform').text()).toBe('Este es el negocio de ERPlora: no tiene plan.');
  });

  it('offers nothing to upgrade, names no plan, gives no verdict and asks erplora.com for nothing', async () => {
    document.head.innerHTML = `<script id="hub-home" type="application/json">${JSON.stringify({ name: 'ERPlora', plan_url: '' })}</script>`;
    const m = await open(OWN);
    for (const id of ['upgrade', 'managed', 'verdict']) expect(m.part(id).exists(), id).toBe(false);
    expect(m.wrapper.find('h2').exists()).toBe(false);
    expect(m.asked).toEqual([]);
  });

  it('says what it uses with no limit, bar or pill', async () => {
    const m = await open(OWN);
    expect(m.part('included-heading').text()).toBe('What you use');
    const amounts = ['files', 'apps', 'people', 'devices', 'capacity'].map((id) => m.part(`row-${id}`).find('.system-usage-amount').text());
    expect(amounts).toEqual(['2 GB', '2', '3', '1', '2 connections']);
    expect(m.wrapper.findAll('[data-testid^="system-usage-row-"]')).toHaveLength(5);
    expect(m.wrapper.find('[role="progressbar"]').exists()).toBe(false);
    expect(m.wrapper.find('.status-pill').exists()).toBe(false);
    expect(m.part('info-requests').text()).toContain('18,420');
  });

  it('a capacity that fell short says the times, and never to upgrade nor whom to tell', async () => {
    const m = await open({ ...OWN, connections: { ...OWN.connections, busy_last_7_days: 4 } });
    expect(m.part('row-capacity').text()).toContain('Fell short 4 times this week');
    expect(m.part('row-capacity').text()).not.toContain('maximum capacity');
    expect(m.part('verdict').exists()).toBe(false);
  });

  it('a business whose plan has not come yet still says it will', async () => {
    const m = await open({ ...OWN, platform: false });
    expect(m.part('unknown').text()).toBe("We do not know this business's plan yet: it shows up as soon as erplora.com sends it.");
    expect(m.part('platform').exists()).toBe(false);
  });
});
