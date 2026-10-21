// A ready-made automation set up with a fault its app already fixed (WORKBOOK FLOW-F36; the old module's
// FLOWS-F11): above «Your automations», a notice per automation built from an older version that starts in
// more cases than its app meant, with «Update it» (`flow.recipe.repair`), which only changes when it starts.
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { RecipeListOut, RecipeOut } from '../operations';
import { click, mountFlow, settle } from '../__tests__/mount-flow';
import RecipeRepairs from './RecipeRepairs.vue';

const mocks = vi.hoisted(() => ({ toastSuccess: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: mocks.toastSuccess,
}));
afterEach(() => mocks.toastSuccess.mockClear());

const OP = 'flow.recipe.list';
const GAP: RecipeOut = {
  ref: 'appointment/customer_cancelled',
  app: 'appointment',
  app_name: 'Appointments',
  icon: 'ion:calendar-outline',
  id: 'customer_cancelled',
  name: 'Fill the gap when a customer cancels',
  summary: '',
  description: '',
  trigger: { kind: 'event', event: 'appointment.appointment.cancelled' },
  steps: [],
  grants: [],
  installed: { flow_id: 'f1', name: 'My gap', enabled: true, outdated: true, missing_grants: [], repair: { 'input.by_customer': { eq: true } } },
};

async function setup(data: RecipeListOut, answers: Record<string, [number, unknown]> = {}) {
  const m = await mountFlow(RecipeRepairs, { answers });
  await m.live();
  await m.result(OP, data);
  return m;
}

describe('A fault its app already fixed', () => {
  it('says which automation starts in more cases than it should, and offers «Update it»', async () => {
    const m = await setup({ recipes: [GAP], set_aside: [] });
    const notice = m.find('flow-repair-appointment/customer_cancelled');
    expect(notice.text()).toContain('«My gap» was set up with an older version of Appointments that starts in more cases than it should.');
    expect(notice.text()).toContain('Updating it only changes when it starts');
    expect(m.find('flow-repair-run-appointment/customer_cancelled').exists()).toBe(true);
  });

  it('shows nothing when there is nothing to repair', async () => {
    const fine = { ...GAP, installed: { ...GAP.installed!, repair: {} } };
    const m = await setup({ recipes: [fine, { ...GAP, ref: 'x/y', installed: null }], set_aside: [] });
    expect(m.find('flow-repairs').exists()).toBe(false);
  });

  it('«Update it» repairs it and says so', async () => {
    const m = await setup({ recipes: [GAP], set_aside: [] }, { '/api/flow/recipes/repair': [200, { id: 'f1' }] });
    await click(m.find('flow-repair-run-appointment/customer_cancelled').element);
    await settle();
    expect(m.sent().find((call) => call.path === '/api/flow/recipes/repair')?.body).toEqual({ recipe: 'appointment/customer_cancelled' });
    expect(mocks.toastSuccess).toHaveBeenCalledWith('«My gap» now only starts when it should.');
  });

  it('a refusal is said in its notice, which stays', async () => {
    const refusal = { error: { code: 'flow.recipe_not_on', message: 'This business has not turned that automation on: there is nothing to change.' } };
    const m = await setup({ recipes: [GAP], set_aside: [] }, { '/api/flow/recipes/repair': [404, refusal] });
    await click(m.find('flow-repair-run-appointment/customer_cancelled').element);
    await settle();
    expect(m.find('flow-repair-error-appointment/customer_cancelled').text()).toContain('there is nothing to change');
    expect(m.find('flow-repair-appointment/customer_cancelled').exists()).toBe(true);
  });

  it('in Spanish', async () => {
    const m = await mountFlow(RecipeRepairs, { locale: 'es' });
    await m.live();
    await m.result(OP, { recipes: [{ ...GAP, app_name: 'Citas' }], set_aside: [] });
    expect(m.find('flow-repair-appointment/customer_cancelled').text()).toContain('«My gap» se montó con una versión anterior de Citas');
    expect(m.find('flow-repair-run-appointment/customer_cancelled').text()).toBe('Actualizarla');
  });
});
