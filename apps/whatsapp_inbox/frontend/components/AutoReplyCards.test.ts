// Settings → «What do you use it for?» (WHATSAPP_INBOX-F14 to F18): the cards «Book appointments» and «Book a table»
// turn the inbox's automatic answer and its notice on and off in Automatizaciones (`flow.recipe.*`), one answer at a
// time on the number (whatsapp_inbox#284); the switch of how the bookings confirm writes Citas' or Reservas' rule
// (F16), in full words on a phone (whatsapp_inbox#285); a newer version is offered with «Update» (F18). Without Citas
// (or Reservas) its card does not show; without Automatizaciones it says so with «See apps».
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ADMIN, click, errorFrame, flush, type MountOptions, mountInbox } from '../__tests__/mount-inbox';
import AutoReplyCards from './AutoReplyCards.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));

afterEach(() => mocks.confirm.mockReset());

const RECIPES = 'flow.recipe.list';
const BOOKING = 'whatsapp_inbox/appointment_from_whatsapp';
const BOOKING_NOTICE = 'whatsapp_inbox/appointment_confirmed';
const TABLE = 'whatsapp_inbox/reservation_from_whatsapp';
const TABLE_NOTICE = 'whatsapp_inbox/reservation_confirmed';

const OWNER: SessionMe = {
  ...ADMIN,
  permissions: [...ADMIN.permissions, 'flow.view', 'flow.manage', 'appointment.manage_settings', 'reservation.manage_settings'],
  apps: [
    { label: 'flow', state: 'on' },
    { label: 'appointment', state: 'on' },
    { label: 'reservation', state: 'on' },
  ],
};

type Installed = { enabled: boolean; outdated?: boolean } | null;

function recipe(ref: string, installed: Installed = null) {
  const [app, id] = ref.split('/');
  return {
    ref,
    app,
    app_name: 'WhatsApp inbox',
    icon: 'ion:chatbubbles-outline',
    id,
    name: id,
    summary: '',
    description: '',
    trigger: { kind: 'manual' },
    steps: [],
    grants: [],
    installed: installed && {
      flow_id: `flow-${id}`,
      name: id,
      enabled: installed.enabled,
      outdated: installed.outdated ?? false,
      missing_grants: [],
      repair: {},
    },
  };
}

function shelf(installed: Record<string, Installed> = {}, setAside: { ref: string; apps: string[] }[] = []) {
  const refs = [BOOKING, BOOKING_NOTICE, TABLE, TABLE_NOTICE].filter((ref) => !setAside.some((item) => item.ref === ref));
  return {
    recipes: refs.map((ref) => recipe(ref, installed[ref] ?? null)),
    set_aside: setAside.map(({ ref, apps }) => ({
      ref,
      app: 'whatsapp_inbox',
      app_name: 'WhatsApp inbox',
      name: ref,
      code: 'flow.recipe_needs_apps',
      message: 'It needs apps this business does not have.',
      apps,
    })),
  };
}

type Answer = { status?: number; body?: unknown };

/** Answers each command by its path (and, for the recipes, the recipe it names), in order: the first not scripted
 *  is a 200 with an empty object. */
function api(script: Record<string, Answer[]> = {}) {
  return ({ url, init }: { url: string; init: RequestInit }) => {
    const path = new URL(url, 'http://a.localhost').pathname;
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
    const key = body.recipe ? `${path} ${body.recipe}` : path;
    const next = script[key]?.shift() ?? script[path]?.shift() ?? {};
    return Response.json(next.body ?? {}, { status: next.status ?? 200 });
  };
}

async function mount(options: MountOptions & { recipes?: unknown } = {}) {
  const page = await mountInbox(AutoReplyCards, { session: OWNER, path: '/whatsapp_inbox/settings', ...options });
  await page.live();
  if (options.recipes !== undefined) await page.result(RECIPES, options.recipes);
  return page;
}

/** The commands made, as `<path> <recipe>` (recipes) or `<path> <body>` (settings). */
function commands(page: Awaited<ReturnType<typeof mount>>): string[] {
  return page
    .sent()
    .filter((call) => call.method === 'POST')
    .map((call) => {
      const body = call.body as Record<string, unknown>;
      return body.recipe ? `${call.path.split('/').pop()} ${body.recipe}` : `${call.path} ${JSON.stringify(body)}`;
    });
}

const card = (page: Awaited<ReturnType<typeof mount>>, which: 'appointments' | 'tables') =>
  page.find(`whatsapp-inbox-autoreply-${which}`);

describe('the cards', () => {
  it('says it is loading, then shows both cards off with what each does and «Turn on»', async () => {
    const page = await mount();
    expect(page.find('whatsapp-inbox-autoreply-loading').exists()).toBe(true);
    await page.result(RECIPES, shelf());
    expect(page.find('whatsapp-inbox-autoreply-title').text()).toBe('What do you use it for?');
    expect(card(page, 'appointments').text()).toContain('Book appointments');
    expect(card(page, 'appointments').text()).toContain('reads your diary');
    expect(card(page, 'appointments').text()).toContain('Off');
    expect(card(page, 'tables').text()).toContain('Book a table');
    expect(page.find('whatsapp-inbox-autoreply-appointments-on').text()).toBe('Turn on');
  });

  it('paints in Spanish', async () => {
    const page = await mount({ locale: 'es', recipes: shelf({ [TABLE]: { enabled: true } }) });
    expect(page.find('whatsapp-inbox-autoreply-title').text()).toBe('¿Para qué lo usas?');
    expect(card(page, 'appointments').text()).toContain('Reservar citas');
    expect(card(page, 'tables').text()).toContain('Activa');
    expect(page.find('whatsapp-inbox-autoreply-tables-off').text()).toBe('Desactivar');
  });

  it('without Citas the appointments card does not show, and the table one still does', async () => {
    const session = { ...OWNER, apps: OWNER.apps.filter((app) => app.label !== 'appointment') };
    const page = await mount({ session, recipes: shelf({}, [{ ref: BOOKING, apps: ['appointment'] }, { ref: BOOKING_NOTICE, apps: ['appointment'] }]) });
    expect(card(page, 'appointments').exists()).toBe(false);
    expect(card(page, 'tables').exists()).toBe(true);
  });

  it('without Automatizaciones each card says it needs it and «See apps» leads to the apps', async () => {
    const session = { ...OWNER, apps: OWNER.apps.filter((app) => app.label !== 'flow') };
    const page = await mount({ session });
    expect(page.find('whatsapp-inbox-autoreply-loading').exists()).toBe(false);
    expect(card(page, 'appointments').text()).toContain('“Book appointments” needs the app Automations.');
    await click(page.find('whatsapp-inbox-autoreply-appointments-apps').element);
    await flush();
    expect(page.router.currentRoute.value.path).toBe('/apps');
  });

  it('without Clientes the card names the app its answer needs, offers «See apps» and never «Turn on»', async () => {
    const page = await mount({
      locale: 'es',
      recipes: shelf({}, [{ ref: BOOKING, apps: ['customer'] }, { ref: BOOKING_NOTICE, apps: ['customer'] }]),
    });
    expect(card(page, 'appointments').text()).toContain('“Reservar citas” necesita la aplicación Clientes.');
    expect(page.find('whatsapp-inbox-autoreply-appointments-on').exists()).toBe(false);
    expect(card(page, 'appointments').text()).not.toContain('Desactivada');
    expect(page.find('whatsapp-inbox-autoreply-tables-on').exists()).toBe(true);
    await click(page.find('whatsapp-inbox-autoreply-appointments-apps').element);
    await flush();
    expect(page.router.currentRoute.value.path).toBe('/apps');
    expect(commands(page)).toEqual([]);
  });

  it('says why the list could not be read, with «Try again»', async () => {
    const page = await mount();
    page.net.lastStream().push(errorFrame(page.subId(RECIPES), 'boom'));
    await flush();
    expect(page.find('whatsapp-inbox-autoreply-error').text()).toContain('The automatic answers could not be loaded.');
  });

  it('with both answers on (from Automatizaciones) each card warns that every message gets two', async () => {
    const page = await mount({ recipes: shelf({ [BOOKING]: { enabled: true }, [TABLE]: { enabled: true } }) });
    expect(page.find('whatsapp-inbox-autoreply-appointments-both').text()).toBe(
      '“Book a table” is on too: each message gets two automatic answers. Turn off the one you do not use.',
    );
    expect(page.find('whatsapp-inbox-autoreply-tables-both').text()).toContain('“Book appointments” is on too');
  });
});

describe('turning one on (F14, F15)', () => {
  it('asks first and turns on the answer and its notice', async () => {
    mocks.confirm.mockResolvedValue(true);
    const page = await mount({ recipes: shelf(), api: api() });
    await click(page.find('whatsapp-inbox-autoreply-appointments-on').element);
    expect(mocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        message:
          'WhatsApp will answer by itself: it reads your diary, offers the free times, and books or moves the appointment of the customer who writes once you say yes.',
        confirmLabel: 'Turn on',
        cancelLabel: 'Not now',
      }),
    );
    expect(commands(page)).toEqual([`enable ${BOOKING}`, `enable ${BOOKING_NOTICE}`]);
    await page.result(RECIPES, shelf({ [BOOKING]: { enabled: true }, [BOOKING_NOTICE]: { enabled: true } }), {}, 2);
    expect(card(page, 'appointments').text()).toContain('On');
    expect(page.find('whatsapp-inbox-autoreply-appointments-done').text()).toBe(
      'Done. Write to yourself from another phone: “I want an appointment tomorrow”.',
    );
  });

  it('«Not now» turns nothing on', async () => {
    mocks.confirm.mockResolvedValue(false);
    const page = await mount({ recipes: shelf(), api: api() });
    await click(page.find('whatsapp-inbox-autoreply-tables-on').element);
    expect(commands(page)).toEqual([]);
  });

  it('with the other answer on, says it goes off and turns it and its notice off first', async () => {
    mocks.confirm.mockResolvedValue(true);
    const page = await mount({ recipes: shelf({ [BOOKING]: { enabled: true }, [BOOKING_NOTICE]: { enabled: true } }), api: api() });
    await click(page.find('whatsapp-inbox-autoreply-tables-on').element);
    expect(mocks.confirm.mock.calls[0][0].consequences).toEqual([
      'Only one automatic answer can answer on your number: turning this one on turns «Book appointments» off.',
    ]);
    expect(commands(page)).toEqual([
      `disable ${BOOKING_NOTICE}`,
      `disable ${BOOKING}`,
      `enable ${TABLE}`,
      `enable ${TABLE_NOTICE}`,
    ]);
  });

  it('when it fails it says why, pauses what it turned on and turns the other answer back on', async () => {
    mocks.confirm.mockResolvedValue(true);
    const failing = api({
      [`/api/flow/recipes/enable ${TABLE_NOTICE}`]: [{ status: 409, body: { error: { code: 'flow.recipe_invalid', message: 'It does not read as an automation.' } } }],
    });
    const page = await mount({ recipes: shelf({ [BOOKING]: { enabled: true } }), api: failing });
    await click(page.find('whatsapp-inbox-autoreply-tables-on').element);
    expect(commands(page)).toEqual([
      `disable ${BOOKING}`,
      `enable ${TABLE}`,
      `enable ${TABLE_NOTICE}`,
      `disable ${TABLE}`,
      `enable ${BOOKING}`,
    ]);
    expect(page.find('whatsapp-inbox-autoreply-tables-error').text()).toBe('It does not read as an automation.');
  });

  it('without the permission it says only an owner or an admin may', async () => {
    mocks.confirm.mockResolvedValue(true);
    const denied = api({ [`/api/flow/recipes/enable ${BOOKING}`]: [{ status: 403, body: { error: { code: 'permission_denied', message: 'Permission “flow.manage” is required.' } } }] });
    const page = await mount({ recipes: shelf(), api: denied });
    await click(page.find('whatsapp-inbox-autoreply-appointments-on').element);
    expect(page.find('whatsapp-inbox-autoreply-appointments-error').text()).toBe('Only an owner or an admin can turn it on.');
  });
});

describe('turning one off (F17)', () => {
  it('pauses its notice first and the answer last', async () => {
    const page = await mount({ recipes: shelf({ [TABLE]: { enabled: true }, [TABLE_NOTICE]: { enabled: true } }), api: api() });
    await click(page.find('whatsapp-inbox-autoreply-tables-off').element);
    expect(commands(page)).toEqual([`disable ${TABLE_NOTICE}`, `disable ${TABLE}`]);
  });

  it('says why when it cannot', async () => {
    const failing = api({ [`/api/flow/recipes/disable ${TABLE}`]: [{ status: 500, body: { error: { code: 'internal_error', message: 'Something failed.' } } }] });
    const page = await mount({ recipes: shelf({ [TABLE]: { enabled: true } }), api: failing });
    await click(page.find('whatsapp-inbox-autoreply-tables-off').element);
    expect(page.find('whatsapp-inbox-autoreply-tables-error').text()).toBe('Something failed.');
  });
});

describe('updating to the improved version (F18)', () => {
  it('offers «Update» only when there is one, asks first and restores what is outdated', async () => {
    mocks.confirm.mockResolvedValue(true);
    const page = await mount({
      recipes: shelf({ [BOOKING]: { enabled: true, outdated: true }, [BOOKING_NOTICE]: { enabled: true } }),
      api: api(),
    });
    expect(page.find('whatsapp-inbox-autoreply-tables-update').exists()).toBe(false);
    expect(page.find('whatsapp-inbox-autoreply-appointments-outdated').text()).toContain('There is an improved version of this automatic answer.');
    await click(page.find('whatsapp-inbox-autoreply-appointments-update').element);
    expect(mocks.confirm.mock.calls[0][0].message).toBe(
      'The new one replaces the current one, also the changes made by hand, and it stays on or paused as it is.',
    );
    expect(commands(page)).toEqual([`restore ${BOOKING}`]);
    expect(page.find('whatsapp-inbox-autoreply-appointments-updated').text()).toBe(
      'Done: this automatic answer already works with the latest version.',
    );
  });

  it('says it no longer exists when it was deleted meanwhile', async () => {
    mocks.confirm.mockResolvedValue(true);
    const gone = api({ [`/api/flow/recipes/restore ${BOOKING}`]: [{ status: 404, body: { error: { code: 'not_found', message: 'gone' } } }] });
    const page = await mount({ recipes: shelf({ [BOOKING]: { enabled: false, outdated: true } }), api: gone });
    await click(page.find('whatsapp-inbox-autoreply-appointments-update').element);
    expect(page.find('whatsapp-inbox-autoreply-appointments-error').text()).toBe(
      'This automatic answer no longer exists here: turn it on again.',
    );
  });
});

describe('how the bookings confirm (F16)', () => {
  it('shows the choice under a card that is on, and nothing under one that is off', async () => {
    const page = await mount({ recipes: shelf({ [BOOKING]: { enabled: true } }) });
    expect(page.find('whatsapp-inbox-autoreply-appointments-confirm').exists()).toBe(true);
    expect(page.find('whatsapp-inbox-autoreply-tables-confirm').exists()).toBe(false);
    await page.reopen();
    expect(page.params('appointment.settings.get')).toEqual([{}]);
    expect(page.params('reservation.settings.get')).toEqual([]);
  });
});
