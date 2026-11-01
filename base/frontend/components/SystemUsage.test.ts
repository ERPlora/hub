// System › «Usage and plan» (BASE-F40; it joins the old Resources and «Plan and limits»), for who runs the business: whoever
// opens it knows in one line whether to upgrade, sees what the plan includes the fullest first, and what no plan limits.
// What was not measured yet says so, never with a zero; the assistant, which waits on erplora.com, fails on its own row.
// «PostgreSQL», «Database of its own», «Cloud», CPU and memory are gone.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import type { AssistantUsage, PlanMeter, PlanUsage } from '../operations';
import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import SystemUsage from './SystemUsage.vue';

const OP = 'base.plan.usage';
const GB = 1024 ** 3;
const PLAN_URL = 'http://localhost:8001/store/plans?business=0199a1b2-0000-7000-8000-000000000001';

const FIGURES: PlanUsage = {
  known: true,
  demo: false,
  plan_slug: 'starter',
  people: { used: 3, limit: 5 },
  devices: { used: 1, limit: 3 },
  apps: { used: 7, limit: 10 },
  database: { available: true, bytes: 312 * 1024 * 1024, day: '2026-10-30' },
  files: { bytes: 2 * GB, day: '2026-10-30', limit: 5 * GB, percent: 40, status: 'within' },
  connections: { peak_today: 2, limit: 3, busy_last_7_days: 0, busy_since: null, bigger_plan_gives_more: true },
  requests: { this_month: 18420, since: null },
  activity: { active_now: 2, last_30_days: 6, day: '2026-10-30' },
  meters: [],
};
const WHATSAPP: PlanMeter = { key: 'whatsapp_inbox', label: 'WhatsApp', used: 40, limit: 150, available: true };
const MESSAGES: AssistantUsage = { used: 120, limit: 300, resets_at: null, demo: false };

const figures = (parts: Partial<PlanUsage> = {}): PlanUsage => ({ ...FIGURES, ...parts });
const NEAR_FILES = { ...FIGURES.files, bytes: 4.2 * GB, percent: 84, status: 'near' } as const;
const FULL_FILES = { ...FIGURES.files, bytes: 5 * GB, percent: 100, status: 'full' } as const;
const FELL_SHORT = { ...FIGURES.connections, busy_last_7_days: 4 };
const TOP_PLAN = { ...FELL_SHORT, peak_today: 6, limit: 6, bigger_plan_gives_more: false };

function embed(block: object | null) {
  document.head.innerHTML = block
    ? `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>`
    : '';
}

async function open(
  usage?: PlanUsage,
  options: Parameters<typeof mountBase>[1] & { assistant?: AssistantUsage | 'failed' | 'waiting' } = {},
) {
  const { assistant = MESSAGES, ...rest } = options;
  const asked: string[] = [];
  const m = await mountBase(SystemUsage, {
    onApi: ({ url }) => {
      const path = url.replace(/^.*\/api/, '/api');
      asked.push(path);
      if (assistant === 'waiting') return new Promise<Response>(() => {});
      if (assistant === 'failed') return Response.json({ error: { code: 'base.assistant_unavailable', message: 'No' } }, { status: 503 });
      return Response.json(assistant);
    },
    ...rest,
  });
  const call = await m.live();
  if (usage) {
    await m.result(call, OP, usage);
    await flush();
  }
  const part = (id: string) => m.wrapper.find(`[data-testid="system-usage-${id}"]`);
  const row = (id: string) => part(`row-${id}`);
  return { ...m, call, part, row, asked };
}

afterEach(() => {
  applySurface('web');
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('SystemUsage', () => {
  it('reads the usage live, saying so meanwhile', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{}]);
    expect(m.part('loading').text()).toBe('Reading the system…');
  });

  describe('the line at the top', () => {
    it('with room: «Your plan is enough», in green', async () => {
      const m = await open(figures());
      expect(m.part('verdict').attributes('data-tone')).toBe('success');
      expect(m.part('verdict').text()).toContain('Your plan is enough');
    });

    it('files from 80 %: «You should upgrade», in amber, with its motive', async () => {
      const m = await open(figures({ files: NEAR_FILES }));
      expect(m.part('verdict').attributes('data-tone')).toBe('warning');
      expect(m.part('verdict').text()).toContain('You should upgrade: you are almost out of space for files');
    });

    it('files full: «You have to upgrade», in red', async () => {
      const m = await open(figures({ files: FULL_FILES }));
      expect(m.part('verdict').attributes('data-tone')).toBe('danger');
      expect(m.part('verdict').text()).toContain('You have to upgrade: no more files fit');
    });

    it('capacity that fell short when a bigger plan helps: red', async () => {
      const m = await open(figures({ connections: FELL_SHORT }));
      expect(m.part('verdict').attributes('data-tone')).toBe('danger');
      expect(m.part('verdict').text()).toContain('You have to upgrade: your business runs out of capacity at its busiest moments');
    });

    it('the assistant’s messages, near and spent, once they answer', async () => {
      const near = await open(figures(), { assistant: { ...MESSAGES, used: 240 } });
      expect(near.part('verdict').text()).toContain("You should upgrade: the assistant's messages are almost spent this month");
      near.wrapper.unmount();
      const spent = await open(figures(), { assistant: { ...MESSAGES, used: 300 } });
      expect(spent.part('verdict').attributes('data-tone')).toBe('danger');
      expect(spent.part('verdict').text()).toContain("You have to upgrade: the assistant's messages are spent this month");
    });

    it('an app’s messages, near and spent', async () => {
      const near = await open(figures({ meters: [{ ...WHATSAPP, used: 120 }] }));
      expect(near.part('verdict').text()).toContain('You should upgrade: WhatsApp messages are almost spent this month');
      near.wrapper.unmount();
      const spent = await open(figures({ meters: [{ ...WHATSAPP, used: 150 }] }));
      expect(spent.part('verdict').attributes('data-tone')).toBe('danger');
      expect(spent.part('verdict').text()).toContain('You have to upgrade: WhatsApp messages are spent this month');
    });

    it('people, devices and apps at their limit stay green, and say so under the line', async () => {
      const m = await open(figures({ people: { used: 5, limit: 5 }, devices: { used: 3, limit: 3 } }));
      expect(m.part('verdict').attributes('data-tone')).toBe('success');
      expect(m.part('verdict').text()).toContain('Your plan is enough');
      expect(m.part('verdict').text()).toContain('People and Devices at the limit: to add more, upgrade the plan.');
      expect(m.row('people').text()).toContain('Full');
    });

    it('at their limit under an amber line it says only the motive', async () => {
      const m = await open(figures({ people: { used: 5, limit: 5 }, files: NEAR_FILES }));
      expect(m.part('verdict').text()).not.toContain('at the limit');
    });
  });

  describe('the plan and how to upgrade', () => {
    it('names the plan, with «Upgrade plan» to this business’s plan page', async () => {
      embed({ name: 'Bar', plan_url: PLAN_URL });
      const m = await open(figures());
      expect(m.wrapper.find('h2').text()).toBe('Starter plan');
      const link = m.part('upgrade');
      expect(link.text()).toBe('Upgrade plan');
      expect([link.attributes('href'), link.attributes('target'), link.attributes('rel')]).toEqual([PLAN_URL, '_blank', 'noopener']);
    });

    it('in the installed app, no button: where plans are managed', async () => {
      embed({ name: 'Bar', plan_url: PLAN_URL });
      applySurface('mobile');
      const m = await open(figures());
      expect(m.part('upgrade').exists()).toBe(false);
      expect(m.part('managed').text()).toBe('Plans are managed from your ERPlora account, on erplora.com.');
    });

    it('where the link does not come, no button: where plans are managed', async () => {
      embed(null);
      const m = await open(figures());
      expect(m.part('upgrade').exists()).toBe(false);
      expect(m.part('managed').exists()).toBe(true);
    });

    it('a plan it has no word for goes by its own name', async () => {
      const m = await open(figures({ plan_slug: 'custom-deal' }));
      expect(m.wrapper.find('h2').text()).toBe('Custom-deal plan');
    });
  });

  describe('what the plan includes', () => {
    it('goes from the fullest down, with capacity last', async () => {
      const m = await open(figures({ files: NEAR_FILES, meters: [WHATSAPP] }));
      expect(m.part('included-heading').text()).toBe('What your plan includes');
      const order = m.wrapper.findAll('[data-testid^="system-usage-row-"]').map((row) => row.attributes('data-testid'));
      expect(order).toEqual(
        ['files', 'apps', 'people', 'assistant', 'devices', 'whatsapp_inbox', 'capacity'].map((id) => `system-usage-row-${id}`),
      );
    });

    it('says each figure, with a bar in the line’s colour and its pill', async () => {
      const m = await open(figures({ files: NEAR_FILES, meters: [WHATSAPP] }));
      expect(m.row('files').text()).toContain('Files');
      expect(m.row('files').text()).toContain('4.2 GB of 5 GB');
      expect(m.row('files').text()).toContain('Close');
      expect(m.row('files').text()).toContain('Measured on Oct 30, 2026');
      expect(m.row('files').get('.usage-meter').attributes('data-tone')).toBe('warning');
      expect(m.row('files').get('[role="progressbar"]').attributes('aria-valuenow')).toBe('84');
      expect(m.row('apps').text()).toContain('7 of 10');
      expect(m.row('people').text()).toContain('3 of 5');
      expect(m.row('devices').text()).toContain('1 of 3');
      expect(m.row('assistant').text()).toContain('120 of 300 a month');
      expect(m.row('whatsapp_inbox').text()).toContain('WhatsApp');
      expect(m.row('whatsapp_inbox').text()).toContain('40 of 150 a month');
    });

    it('below 80 % the bar stays green, whatever the meter would say by itself at 79 %', async () => {
      const m = await open(figures({ files: { ...FIGURES.files, bytes: 3.95 * GB, percent: 79, status: 'within' } }));
      expect(m.row('files').get('.usage-meter').attributes('data-tone')).toBe('success');
    });

    it('at their limit: «Full» and still green', async () => {
      const m = await open(figures({ devices: { used: 1, limit: 1 } }));
      expect(m.row('devices').text()).toContain('Full');
      expect(m.row('devices').get('.usage-meter').attributes('data-tone')).toBe('success');
    });

    it('with no limit: «No limit» and no bar', async () => {
      const m = await open(figures({ people: { used: 3, limit: null } }));
      expect(m.row('people').text()).toContain('3 · No limit');
      expect(m.row('people').find('[role="progressbar"]').exists()).toBe(false);
    });

    it('files before the first night: when the first figure comes, no bar', async () => {
      const m = await open(figures({ files: { bytes: null, day: null, limit: 5 * GB, percent: null, status: null } }));
      expect(m.row('files').text()).toContain('Measured every night: the first figure comes tomorrow.');
      expect(m.row('files').find('[role="progressbar"]').exists()).toBe(false);
    });

    it('the assistant with 0: what the plan does not include, and no motive', async () => {
      const m = await open(figures(), { assistant: { ...MESSAGES, used: 0, limit: 0 } });
      expect(m.row('assistant').text()).toContain('Your plan does not include the assistant');
      expect(m.row('assistant').find('[role="progressbar"]').exists()).toBe(false);
      expect(m.part('verdict').attributes('data-tone')).toBe('success');
    });

    it('the assistant failing says so on its row, with no figure, and the screen goes on', async () => {
      const m = await open(figures(), { assistant: 'failed' });
      expect(m.row('assistant').text()).toContain('Not available right now');
      expect(m.row('assistant').text()).not.toMatch(/\d/);
      expect(m.row('files').exists()).toBe(true);
      expect(m.part('verdict').attributes('data-tone')).toBe('success');
    });

    it('while the assistant answers its row says it is reading', async () => {
      const m = await open(figures(), { assistant: 'waiting' });
      expect(m.row('assistant').text()).toContain('Reading…');
      expect(m.row('files').exists()).toBe(true);
    });

    it('asks the assistant apart, and only once the plan is known', async () => {
      const m = await open();
      expect(m.asked).toEqual([]);
      await m.result(m.call, OP, figures());
      await flush();
      expect(m.asked).toEqual(['/api/assistant/usage']);
      await m.result(m.call, OP, figures({ people: { used: 4, limit: 5 } }));
      await flush();
      expect(m.asked).toEqual(['/api/assistant/usage']);
    });

    it('an app whose plan includes none, one that failed and one not measured yet', async () => {
      const none = await open(figures({ meters: [{ ...WHATSAPP, used: 0, limit: 0 }] }));
      expect(none.row('whatsapp_inbox').text()).toContain('Your plan does not include WhatsApp');
      none.wrapper.unmount();
      const failed = await open(figures({ meters: [{ ...WHATSAPP, used: null, limit: null, available: false }] }));
      expect(failed.row('whatsapp_inbox').text()).toContain('Not available right now');
      failed.wrapper.unmount();
      const waiting = await open(figures({ meters: [{ ...WHATSAPP, used: null, limit: null }] }));
      expect(waiting.row('whatsapp_inbox').text()).toContain('Not measured yet.');
    });
  });

  describe('capacity', () => {
    it('is called so, with its connections under it; nothing more when it never fell short', async () => {
      const m = await open(figures());
      expect(m.row('capacity').text()).toContain('Capacity');
      expect(m.row('capacity').text()).toContain('2 of 3 connections');
      expect(m.row('capacity').text()).not.toContain('fell short');
      expect(m.row('capacity').get('.usage-meter').attributes('data-tone')).toBe('success');
    });

    it('says how many times it fell short this week', async () => {
      const many = await open(figures({ connections: FELL_SHORT }));
      expect(many.row('capacity').text()).toContain('fell short 4 times this week');
      expect(many.row('capacity').get('.usage-meter').attributes('data-tone')).toBe('danger');
      many.wrapper.unmount();
      const once = await open(figures({ connections: { ...FELL_SHORT, busy_last_7_days: 1 } }));
      expect(once.row('capacity').text()).toContain('fell short once this week');
    });

    it('counted for less than 7 days says since when', async () => {
      const m = await open(figures({ connections: { ...FELL_SHORT, busy_since: '2026-10-28' } }));
      expect(m.row('capacity').text()).toContain('Since Oct 28, 2026');
    });

    it('a Free plan’s first operation is no alarm', async () => {
      const m = await open(figures({ connections: { ...FIGURES.connections, peak_today: 1, limit: 1 } }));
      expect(m.row('capacity').get('.usage-meter').attributes('data-tone')).toBe('success');
      expect(m.part('verdict').attributes('data-tone')).toBe('success');
    });

    it('a plan with all the service gives never offers to upgrade it: it says where to tell us', async () => {
      embed({ name: 'Bar', plan_url: PLAN_URL });
      const m = await open(figures({ plan_slug: 'pro', connections: TOP_PLAN }));
      expect(m.part('verdict').attributes('data-tone')).toBe('success');
      expect(m.row('capacity').text()).toContain('You already have the maximum capacity: tell us in «Report a problem».');
      expect(m.row('capacity').text()).toContain('6 of 6 connections');
      expect(m.row('capacity').get('.usage-meter').attributes('data-tone')).toBe('success');
      expect(m.row('capacity').find('a').exists()).toBe(false);
    });

    it('with no measure today says so: no bar, never a zero', async () => {
      const m = await open(figures({ connections: { ...FIGURES.connections, peak_today: null } }));
      expect(m.row('capacity').text()).toContain('Not measured today yet.');
      expect(m.row('capacity').find('[role="progressbar"]').exists()).toBe(false);
    });
  });

  describe('for your information', () => {
    it('what no plan limits, with no bar or pill', async () => {
      const m = await open(figures());
      expect(m.part('information-heading').text()).toBe('For your information');
      const info = m.part('information');
      expect(info.find('[role="progressbar"]').exists()).toBe(false);
      expect(m.part('info-requests').text()).toContain('Requests this month');
      expect(m.part('info-requests').text()).toContain('18,420');
      expect(m.part('info-active').text()).toContain('Active now');
      expect(m.part('info-active').text()).toContain('2');
      expect(m.part('info-month').text()).toContain('Last 30 days');
      expect(m.part('info-month').text()).toContain('6');
      expect(m.part('info-month').text()).toContain('Measured on Oct 30, 2026');
      expect(m.part('info-database').text()).toContain('Database size');
      expect(m.part('info-database').text()).toContain('312 MB');
      expect(m.part('info-database').text()).toContain('Measured on Oct 30, 2026');
    });

    it('requests counted since after day 1 say since when; a true zero is a zero', async () => {
      const m = await open(figures({ requests: { this_month: 0, since: '2026-10-09' } }));
      expect(m.part('info-requests').text()).toContain('0');
      expect(m.part('info-requests').text()).toContain('Since Oct 9, 2026');
    });

    it('what was not measured yet says so, never with a zero', async () => {
      const m = await open(
        figures({
          requests: { this_month: null, since: null },
          activity: { active_now: 0, last_30_days: null, day: null },
          database: { available: true, bytes: null, day: null },
        }),
      );
      expect(m.part('info-requests').text()).toContain('Not measured today yet.');
      expect(m.part('info-month').text()).toContain('Measured every night: the first figure comes tomorrow.');
      expect(m.part('info-database').text()).toContain('Measured every night: the first figure comes tomorrow.');
      expect(m.part('info-active').text()).toContain('0');
    });
  });

  it('nothing of what is gone is said', async () => {
    const m = await open(figures());
    expect(m.wrapper.text()).not.toMatch(
      /PostgreSQL|Database of its own|Shared database|Cloud|not measured per business|CPU|memory|Active yesterday/i,
    );
  });

  describe('what the hub does not know', () => {
    it('a demo says it is not measured, with no line, rows or plan', async () => {
      const m = await open(figures({ demo: true, known: false, plan_slug: null }));
      expect(m.part('demo').text()).toBe('Use is not measured in a demo: its data is deleted when it ends.');
      expect(m.wrapper.findAll('[data-testid^="system-usage-row-"]')).toEqual([]);
      expect(m.part('verdict').exists()).toBe(false);
      expect(m.part('information').exists()).toBe(false);
      expect(m.asked).toEqual([]);
    });

    it('without the plan: it says so, with what is in use and no bar, pill, verdict, plan or assistant', async () => {
      embed({ name: 'Bar', plan_url: PLAN_URL });
      const m = await open(
        figures({
          known: false,
          plan_slug: null,
          people: { used: 3, limit: null },
          devices: { used: 1, limit: null },
          apps: { used: 2, limit: null },
          files: { ...FIGURES.files, limit: null, percent: null, status: null },
          connections: { ...FIGURES.connections, limit: null, bigger_plan_gives_more: false },
        }),
      );
      expect(m.part('unknown').text()).toBe("We do not know this business's plan yet: it shows up as soon as erplora.com sends it.");
      expect(m.part('verdict').exists()).toBe(false);
      expect(m.part('upgrade').exists()).toBe(false);
      expect(m.wrapper.find('h2').exists()).toBe(false);
      expect(m.wrapper.find('[role="progressbar"]').exists()).toBe(false);
      expect(m.wrapper.find('.status-pill').exists()).toBe(false);
      expect(m.part('included-heading').text()).toBe('What you use');
      expect(m.row('people').text()).toContain('3');
      expect(m.row('people').text()).not.toContain('No limit');
      expect(m.row('files').text()).toContain('2 GB');
      expect(m.row('capacity').text()).toContain('2 connections');
      expect(m.row('assistant').exists()).toBe(false);
      expect(m.asked).toEqual([]);
    });
  });

  it('a failed read says so, with «Retry»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(m.part('error').text()).toContain('We could not read the system');
    expect(m.part('error').text()).toContain('The figures and the logs are not available right now. You can try again.');
    expect(m.part('retry').exists()).toBe(true);
  });

  it('a failed read after a good one keeps the figures', async () => {
    const m = await open(figures());
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(m.part('error').exists()).toBe(false);
    expect(m.row('files').exists()).toBe(true);
  });

  it('says it all in Spanish, with the flow’s words', async () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const m = await open(
      figures({ plan_slug: 'free', files: NEAR_FILES, connections: FELL_SHORT, meters: [WHATSAPP], people: { used: 5, limit: 5 } }),
      { locale: 'es' },
    );
    expect(m.wrapper.find('h2').text()).toBe('Plan Gratis');
    expect(m.part('upgrade').text()).toBe('Mejorar plan');
    expect(m.part('verdict').text()).toContain('Tienes que ampliar: tu negocio se queda sin capacidad en los momentos de más trabajo');
    expect(m.part('included-heading').text()).toBe('Lo que incluye tu plan');
    expect(m.row('files').text()).toContain('Archivos');
    expect(m.row('files').text()).toContain('4,2 GB de 5 GB');
    expect(m.row('files').text()).toContain('Cerca');
    expect(m.row('files').text()).toContain('Medido el 30 oct 2026');
    expect(m.row('people').text()).toContain('Personas');
    expect(m.row('people').text()).toContain('Completo');
    expect(m.row('apps').text()).toContain('Apps');
    expect(m.row('devices').text()).toContain('Dispositivos');
    expect(m.row('assistant').text()).toContain('Asistente');
    expect(m.row('assistant').text()).toContain('120 de 300 al mes');
    expect(m.row('whatsapp_inbox').text()).toContain('40 de 150 al mes');
    expect(m.row('capacity').text()).toContain('Capacidad');
    expect(m.row('capacity').text()).toContain('2 de 3 conexiones');
    expect(m.row('capacity').text()).toContain('se quedó corta 4 veces esta semana');
    expect(m.part('information-heading').text()).toBe('Para tu información');
    expect(m.part('info-requests').text()).toContain('Peticiones este mes');
    expect(m.part('info-active').text()).toContain('Activas ahora');
    expect(m.part('info-month').text()).toContain('Últimos 30 días');
    expect(m.part('info-database').text()).toContain('Tamaño de la base');
    expect(m.part('info-database').text()).toContain('312 MB');
  });

  it('dice lo demás de la pantalla en español', async () => {
    const line = async (usage: PlanUsage, assistant: AssistantUsage | 'failed' = MESSAGES) => {
      const m = await open(usage, { locale: 'es', assistant });
      const said = m.part('verdict').text();
      m.wrapper.unmount();
      return said;
    };
    expect(await line(figures())).toContain('Tu plan te alcanza');
    expect(await line(figures({ files: NEAR_FILES }))).toContain('Te conviene ampliar: casi no te quedan archivos');
    expect(await line(figures({ files: FULL_FILES }))).toContain('Tienes que ampliar: ya no caben más archivos');
    expect(await line(figures(), { ...MESSAGES, used: 240 })).toContain('Te conviene ampliar: casi no te quedan mensajes del asistente este mes');
    expect(await line(figures(), { ...MESSAGES, used: 300 })).toContain('Tienes que ampliar: se han acabado los mensajes del asistente de este mes');
    expect(await line(figures({ meters: [{ ...WHATSAPP, used: 120 }] }))).toContain('Te conviene ampliar: casi no te quedan mensajes de WhatsApp este mes');
    expect(await line(figures({ meters: [{ ...WHATSAPP, used: 150 }] }))).toContain('Tienes que ampliar: se han acabado los mensajes de WhatsApp de este mes');
    expect(await line(figures({ people: { used: 5, limit: 5 } }))).toContain('Personas al completo: para añadir más, amplía el plan.');
    expect(await line(figures({ people: { used: 5, limit: 5 }, apps: { used: 10, limit: 10 } }))).toContain(
      'Personas y Apps al completo: para añadir más, amplía el plan.',
    );

    const top = await open(figures({ connections: TOP_PLAN, files: { ...FIGURES.files, limit: null, percent: null, status: null } }), { locale: 'es', assistant: { ...MESSAGES, limit: 0, used: 0 } });
    expect(top.row('capacity').text()).toContain('Ya tienes la capacidad máxima: cuéntanoslo en «Reportar un problema».');
    expect(top.row('files').text()).toContain('2 GB · Sin límite');
    expect(top.row('assistant').text()).toContain('Tu plan no incluye asistente');
    top.wrapper.unmount();

    const failed = await open(figures({ meters: [{ ...WHATSAPP, used: 0, limit: 0 }], requests: { this_month: 3, since: '2026-10-09' } }), { locale: 'es', assistant: 'failed' });
    expect(failed.row('assistant').text()).toContain('No disponible ahora');
    expect(failed.row('whatsapp_inbox').text()).toContain('Tu plan no incluye WhatsApp');
    expect(failed.part('info-requests').text()).toContain('Desde el 9 oct 2026');
    failed.wrapper.unmount();

    applySurface('mobile');
    const managed = await open(figures({ connections: { ...FELL_SHORT, peak_today: null, busy_last_7_days: 1 }, files: { bytes: null, day: null, limit: 5 * GB, percent: null, status: null } }), { locale: 'es' });
    expect(managed.part('managed').text()).toBe('Los planes se gestionan desde tu cuenta de ERPlora, en erplora.com.');
    expect(managed.row('files').text()).toContain('Se mide cada noche: la primera cifra llega mañana.');
    expect(managed.row('capacity').text()).toContain('Todavía sin medir hoy.');
    expect(managed.row('capacity').text()).toContain('se quedó corta 1 vez esta semana');
    managed.wrapper.unmount();

    const demo = await open(figures({ demo: true, known: false }), { locale: 'es' });
    expect(demo.part('demo').text()).toBe('En una demo no se mide el uso: sus datos se borran al terminar.');
    demo.wrapper.unmount();

    const unknown = await open(figures({ known: false, plan_slug: null }), { locale: 'es' });
    expect(unknown.part('unknown').text()).toBe('Todavía no conocemos el plan de este negocio: aparecerá en cuanto erplora.com lo envíe.');
    expect(unknown.part('included-heading').text()).toBe('Lo que usas');
  });
});
