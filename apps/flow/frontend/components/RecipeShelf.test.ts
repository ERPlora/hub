// «Comes with …» (WORKBOOK FLOW-F33, F34, F35): the ready-made automations the apps bring, under the
// gallery, one section per app (`flow.recipe.list`, live). A card opens to say what it does and what it may
// do and why, in its app's words; «Turn it on» builds it on with exactly those permissions; once built it
// says how it is and offers «Pause it» or «Turn it on», «See it» and «Restore the factory one» (asked first);
// «New version» when its app brings a newer one. What this business cannot use is said below.
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { RecipeListOut, RecipeOut } from '../operations';
import { click, errorFrame, mountFlow, settle } from '../__tests__/mount-flow';
import RecipeShelf from './RecipeShelf.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), toastSuccess: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: mocks.toastSuccess,
}));
afterEach(() => {
  mocks.confirm.mockReset();
  mocks.toastSuccess.mockClear();
});

const OP = 'flow.recipe.list';
const GAP: RecipeOut = {
  ref: 'appointment/customer_cancelled',
  app: 'appointment',
  app_name: 'Appointments',
  icon: 'ion:calendar-outline',
  id: 'customer_cancelled',
  name: 'Fill the gap when a customer cancels',
  summary: 'When a customer cancels their appointment, leaves you a task to fill the gap.',
  description: 'Only the cancellations the customer asks for.',
  trigger: { kind: 'event', event: 'appointment.appointment.cancelled', filter: { 'input.by_customer': { eq: true } } },
  steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Fill the gap' } }],
  grants: [{ operation: 'task.task.create', reason: 'Leaves you the task, so you remember to offer the free time.' }],
  installed: null,
};
const BOOKED: RecipeOut = { ...GAP, ref: 'online_booking/booked_online', app: 'online_booking', app_name: 'Online booking', id: 'booked_online', name: 'Check each booking made online' };
const ON = { flow_id: 'f1', name: 'Fill the gap when a customer cancels', enabled: true, outdated: false, missing_grants: [], repair: {} };

async function setup(data: RecipeListOut, answers: Record<string, [number, unknown]> = {}) {
  const m = await mountFlow(RecipeShelf, { answers });
  await m.live();
  await m.result(OP, data);
  return m;
}

describe('Comes with …', () => {
  it('shows one section per app that brings some, each card with its name and line', async () => {
    const m = await setup({ recipes: [GAP, BOOKED], set_aside: [] });
    expect(m.find('flow-recipes-appointment').text()).toContain('Comes with Appointments');
    expect(m.find('flow-recipes-online_booking').text()).toContain('Comes with Online booking');
    expect(m.find('flow-recipe-open-appointment/customer_cancelled').text()).toContain('Fill the gap when a customer cancels');
    expect(m.find('flow-recipe-open-appointment/customer_cancelled').text()).toContain('leaves you a task to fill the gap');
  });

  it('says, above its sections, that these come ready and start working at once when turned on (FLOW-F33)', async () => {
    // The gallery's own line above reads «Pick one and it becomes yours, paused»; these do the opposite.
    const m = await setup({ recipes: [GAP], set_aside: [] });
    expect(m.find('flow-recipes-intro').text()).toBe(
      'Your apps bring these ready-made: turn one on and it starts working at once, only with the permissions it names.',
    );
    const es = await mountFlow(RecipeShelf, { locale: 'es' });
    await es.live();
    await es.result(OP, { recipes: [GAP], set_aside: [] });
    expect(es.find('flow-recipes-intro').text()).toBe(
      'Tus apps traen estas ya hechas: enciende una y empieza a funcionar ya, solo con los permisos que nombra.',
    );
  });

  it('shows nothing when no app brings one', async () => {
    const m = await setup({ recipes: [], set_aside: [] });
    expect(m.find('flow-recipes').exists()).toBe(false);
  });

  it('a card opens to say what it does and, in its app’s words, what it may do', async () => {
    const m = await setup({ recipes: [GAP], set_aside: [] });
    await click(m.find('flow-recipe-open-appointment/customer_cancelled').element);
    const panel = m.find('flow-recipe-panel-appointment/customer_cancelled');
    expect(panel.text()).toContain('This automation comes with Appointments.');
    expect(panel.text()).toContain('Only the cancellations the customer asks for.');
    expect(panel.text()).toContain('Leaves you the task, so you remember to offer the free time.');
    expect(panel.text()).toContain('It starts working now, with only these permissions.');
  });

  it('«Turn it on» builds it on with its permissions and says so', async () => {
    const m = await setup({ recipes: [GAP], set_aside: [] }, { '/api/flow/recipes/enable': [200, { created: true, flow: { id: 'f1', name: GAP.name } }] });
    await click(m.find('flow-recipe-open-appointment/customer_cancelled').element);
    await click(m.find('flow-recipe-enable-appointment/customer_cancelled').element);
    await settle();
    expect(m.sent().find((call) => call.path === '/api/flow/recipes/enable')?.body).toEqual({ recipe: 'appointment/customer_cancelled' });
    expect(mocks.toastSuccess).toHaveBeenCalledWith('«Fill the gap when a customer cancels» is on.');
  });

  it('once on, it says so and offers «Pause it», «See it» and «Restore the factory one»', async () => {
    const m = await setup({ recipes: [{ ...GAP, installed: ON }], set_aside: [] }, { '/api/flow/recipes/disable': [200, { id: 'f1' }] });
    expect(m.find('flow-recipe-open-appointment/customer_cancelled').text()).toContain('Active');
    await click(m.find('flow-recipe-open-appointment/customer_cancelled').element);
    expect(m.find('flow-recipe-enable-appointment/customer_cancelled').exists()).toBe(false);
    expect(m.find('flow-recipe-see-appointment/customer_cancelled').exists()).toBe(true);
    await click(m.find('flow-recipe-disable-appointment/customer_cancelled').element);
    await settle();
    expect(m.sent().find((call) => call.path === '/api/flow/recipes/disable')?.body).toEqual({ recipe: 'appointment/customer_cancelled' });
    expect(mocks.toastSuccess).toHaveBeenCalledWith('«Fill the gap when a customer cancels» is paused. Nothing was deleted.');
  });

  it('paused, it offers «Turn it on» again; «See it» opens its automation', async () => {
    const m = await setup({ recipes: [{ ...GAP, installed: { ...ON, enabled: false } }], set_aside: [] });
    expect(m.find('flow-recipe-open-appointment/customer_cancelled').text()).toContain('Paused');
    await click(m.find('flow-recipe-open-appointment/customer_cancelled').element);
    expect(m.find('flow-recipe-enable-appointment/customer_cancelled').exists()).toBe(true);
    await click(m.find('flow-recipe-see-appointment/customer_cancelled').element);
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/flow/automations/f1');
  });

  it('a newer version is flagged; «Restore the factory one» asks first and restores', async () => {
    const m = await setup({ recipes: [{ ...GAP, installed: { ...ON, outdated: true } }], set_aside: [] }, { '/api/flow/recipes/restore': [200, { id: 'f1' }] });
    expect(m.find('flow-recipe-open-appointment/customer_cancelled').text()).toContain('New version');
    await click(m.find('flow-recipe-open-appointment/customer_cancelled').element);
    expect(m.find('flow-recipe-panel-appointment/customer_cancelled').text()).toContain('There is a new version of this automation.');
    mocks.confirm.mockResolvedValue(false);
    await click(m.find('flow-recipe-restore-appointment/customer_cancelled').element);
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Restore the factory version?',
      message: 'Your changes to this automation will be replaced by the version its app brings today. It stays on or paused as it is now.',
      confirmLabel: 'Restore',
      cancelLabel: 'Keep mine',
    });
    expect(m.sent().some((call) => call.path === '/api/flow/recipes/restore')).toBe(false);
    mocks.confirm.mockResolvedValue(true);
    await click(m.find('flow-recipe-restore-appointment/customer_cancelled').element);
    await settle();
    expect(m.sent().find((call) => call.path === '/api/flow/recipes/restore')?.body).toEqual({ recipe: 'appointment/customer_cancelled' });
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Done: this automation is the factory version again.');
  });

  it('a refusal is said inside its card and nothing changes', async () => {
    const refusal = { error: { code: 'permission_denied', message: 'You cannot allow what you may not do yourself: «task.task.create».' } };
    const m = await setup({ recipes: [GAP], set_aside: [] }, { '/api/flow/recipes/enable': [403, refusal] });
    await click(m.find('flow-recipe-open-appointment/customer_cancelled').element);
    await click(m.find('flow-recipe-enable-appointment/customer_cancelled').element);
    await settle();
    expect(m.find('flow-recipe-error-appointment/customer_cancelled').text()).toContain('You cannot allow what you may not do yourself');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });

  it('says which apps the hidden ones need, and why another one cannot be offered', async () => {
    const m = await setup({
      recipes: [GAP],
      set_aside: [
        { ref: 'online_booking/booked_online', app: 'online_booking', app_name: 'Online booking', name: 'Check each booking made online', code: 'flow.recipe_needs_apps', message: '', apps: ['task'] },
        { ref: 'appointment/broken', app: 'appointment', app_name: 'Appointments', name: 'Broken one', code: 'flow.recipe_invalid', message: 'It does not read as an automation: steps.', apps: [] },
      ],
    });
    expect(m.find('flow-recipes-hidden').text()).toBe('Some automations your apps bring are hidden: they need Tasks.');
    expect(m.find('flow-recipes-invalid').text()).toContain('«Broken one» cannot be offered: It does not read as an automation: steps.');
  });

  it('a list that could not be read says so, with «Retry»', async () => {
    const m = await mountFlow(RecipeShelf);
    const stream = await m.live();
    stream.push(errorFrame(m.subId(OP), 'internal_error'));
    await settle();
    expect(m.find('flow-recipes-error').text()).toContain('The automations your apps bring could not be read.');
    expect(m.find('flow-recipes-retry').exists()).toBe(true);
  });
});
