// The Home's health row (BASE-F02): under the greeting, who runs the business sees how each app on says it is (the
// receipt printer, the WhatsApp number), the way to fix what can be fixed and «View system». Nobody else sees it, nor
// asks for it. It reads `base.health.list` when the Home opens and again each time the person comes back to it.
import { StatusPill } from '@erplora/ui/components';
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';
import { ref } from 'vue';

import { EMPLOYEE, flush, mountBase, OWNER } from '../__tests__/mount-base';
import type { HomeHealthItem } from '../operations/home';
import HomeHealthRow from './HomeHealthRow.vue';

const PRINTER_OFF: HomeHealthItem = {
  key: 'printing',
  app: 'printing',
  state: 'no_signal',
  title: 'Printer not connected',
  action: 'Set up printing',
  route: '/printing/printers',
};
const PRINTER_READY: HomeHealthItem = { ...PRINTER_OFF, state: 'ok', title: 'Printer ready', action: null, route: null };
const WHATSAPP_OK: HomeHealthItem = {
  key: 'whatsapp_inbox',
  app: 'whatsapp_inbox',
  state: 'ok',
  title: 'WhatsApp connected',
  action: null,
  route: null,
};
const WHATSAPP_UNKNOWN: HomeHealthItem = { ...WHATSAPP_OK, state: 'unknown', title: "We couldn't check WhatsApp" };

type Answer = () => Response | Promise<Response>;

const told = (...items: HomeHealthItem[]): Answer => () => Response.json({ items });
const failing: Answer = () => Response.json({ error: { code: 'internal', message: 'No' } }, { status: 500 });

afterEach(() => {
  document.body.innerHTML = '';
});

async function settle() {
  for (let i = 0; i < 4; i += 1) await flush();
}

/** The row, with what `base.health.list` answers each time it is asked (the last answer repeats). */
async function row(answers: Answer[], options: Parameters<typeof mountBase>[1] = {}) {
  const asked: string[] = [];
  const m = await mountBase(HomeHealthRow, {
    routes: ['/printing/printers', '/system'],
    onApi: ({ url }) => {
      asked.push(new URL(url, 'http://hub.localhost').pathname);
      return answers[Math.min(asked.length, answers.length) - 1]();
    },
    ...options,
  });
  await settle();
  const items = () =>
    m.wrapper.findAll('[data-testid="home-health-item"]').map((item) => ({
      app: item.attributes('data-app'),
      pill: item.findComponent(StatusPill).props(),
      action: item.find('[data-testid="home-health-action"]').exists()
        ? item.get('[data-testid="home-health-action"]').text()
        : null,
    }));
  return { ...m, asked, items };
}

describe('HomeHealthRow', () => {
  it('tells who runs the business how each app on is, in the order the server gives, with the way to fix it', async () => {
    const m = await row([told(PRINTER_OFF, WHATSAPP_OK)]);

    expect(m.asked).toEqual(['/api/home/health']);
    expect(m.items()).toEqual([
      {
        app: 'printing',
        pill: expect.objectContaining({ label: 'Printer not connected', tone: 'warning', icon: 'ion:warning-outline' }),
        action: 'Set up printing',
      },
      {
        app: 'whatsapp_inbox',
        pill: expect.objectContaining({ label: 'WhatsApp connected', tone: 'success', icon: 'ion:checkmark-circle-outline' }),
        action: null,
      },
    ]);
    expect(m.wrapper.get('[data-testid="home-health"]').attributes('aria-label')).toBe('How your business is working');
  });

  it('its action opens the screen of the app that fixes it, and «View system» opens System', async () => {
    const m = await row([told(PRINTER_OFF)]);

    await m.wrapper.get('[data-testid="home-health-action"]').trigger('click');
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/printing/printers');

    await m.router.push('/');
    await settle();
    await m.wrapper.get('[data-testid="home-health-system"]').trigger('click');
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/system');
  });

  it('says in grey what could not be checked, never as ready, and offers nothing to do about it', async () => {
    const m = await row([told(WHATSAPP_UNKNOWN)]);

    expect(m.items()).toEqual([
      {
        app: 'whatsapp_inbox',
        pill: expect.objectContaining({ label: "We couldn't check WhatsApp", tone: 'neutral', icon: 'ion:help-circle-outline' }),
        action: null,
      },
    ]);
  });

  it('is not there for who does not run the business, which does not even ask', async () => {
    const m = await row([told(PRINTER_OFF)], { session: EMPLOYEE });

    expect(m.wrapper.find('[data-testid="home-health"]').exists()).toBe(false);
    expect(m.asked).toEqual([]);
  });

  it('is not there when no app on says how it is', async () => {
    const m = await row([told()]);

    expect(m.asked).toEqual(['/api/home/health']);
    expect(m.wrapper.find('[data-testid="home-health"]').exists()).toBe(false);
  });

  it('while it reads, it says it is busy', async () => {
    const m = await row([() => new Promise<Response>(() => {})]);

    const section = m.wrapper.get('[data-testid="home-health"]');
    expect(section.attributes('aria-busy')).toBe('true');
    expect(section.find('[data-testid="home-health-loading"]').exists()).toBe(true);
    expect(m.items()).toEqual([]);
  });

  it('when the reading fails it says so, with «Retry», which reads it again', async () => {
    const m = await row([failing, told(PRINTER_READY)]);

    expect(m.wrapper.get('[data-testid="home-health-error"]').text()).toContain("We couldn't check how your business is working");
    expect(m.items()).toEqual([]);

    await m.wrapper.get('[data-testid="home-health-retry"]').trigger('click');
    await settle();

    expect(m.asked).toEqual(['/api/home/health', '/api/home/health']);
    expect(m.wrapper.find('[data-testid="home-health-error"]').exists()).toBe(false);
    expect(m.items().map((item) => item.pill.label)).toEqual(['Printer ready']);
  });

  it('reads it again each time the person comes back to the Home, not while she is elsewhere', async () => {
    const m = await row([told(PRINTER_OFF), told(PRINTER_READY)]);

    await m.router.push('/printing/printers');
    await settle();
    expect(m.asked).toEqual(['/api/home/health']);

    await m.router.push('/');
    await settle();
    expect(m.asked).toEqual(['/api/home/health', '/api/home/health']);
    expect(m.items()).toEqual([
      { app: 'printing', pill: expect.objectContaining({ label: 'Printer ready', tone: 'success' }), action: null },
    ]);
  });

  it('reads it again when the person’s language changes with the Home open (the assistant changed it)', async () => {
    const me = ref<SessionMe>(OWNER);
    const PRINTER_OFF_ES = { ...PRINTER_OFF, title: 'Impresora sin conexión' };
    const m = await row([told(PRINTER_OFF), told(PRINTER_OFF_ES)], { session: me });

    me.value = { ...OWNER, apps: [{ label: 'demo', state: 'on' }] };
    await settle();
    expect(m.asked).toEqual(['/api/home/health']);

    me.value = { ...OWNER, language: 'es' };
    await settle();
    expect(m.asked).toEqual(['/api/home/health', '/api/home/health']);
    expect(m.items()).toEqual([
      { app: 'printing', pill: expect.objectContaining({ label: 'Impresora sin conexión' }), action: 'Set up printing' },
    ]);
  });

  it('for who does not run the business, a new language asks nothing either', async () => {
    const me = ref<SessionMe>(EMPLOYEE);
    const m = await row([told(PRINTER_OFF)], { session: me });

    me.value = { ...EMPLOYEE, language: 'es' };
    await settle();
    expect(m.asked).toEqual([]);
  });

  it('says «View system» in the language of the page', async () => {
    const m = await row([told(PRINTER_OFF)], { locale: 'es' });

    expect(m.wrapper.get('[data-testid="home-health-system"]').text()).toBe('Ver sistema');
    expect(m.wrapper.get('[data-testid="home-health"]').attributes('aria-label')).toBe('Cómo está funcionando tu negocio');
  });
});
