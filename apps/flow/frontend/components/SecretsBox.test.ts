// «Secrets» (WORKBOOK FLOW-F26; the old module's box inside «Call another system»): the names of the
// business's secrets, live; a name and a value to save one, whose value is never shown again; × deletes
// one after asking. Without the server's key it says so and saves nothing.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountFlow, settle } from '../__tests__/mount-flow';
import SecretsBox from './SecretsBox.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), toastSuccess: vi.fn(async () => undefined) }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({ ...(await importOriginal<typeof import('@erplora/ui/shell')>()), toastSuccess: mocks.toastSuccess }));

const OP = 'flow.secret.list';
const ROW = { id: 'x1', name: 'STRIPE_KEY', created_at: '2026-10-15T10:00:00+02:00', updated_at: '2026-10-15T10:00:00+02:00', updated_by: 'ana' };

async function setup(rows = [ROW], available = true) {
  const m = await mountFlow(SecretsBox, { props: { testid: 'flow-secrets' } });
  await m.live();
  await m.result(OP, { rows, available });
  return m;
}

describe('SecretsBox', () => {
  it('lists the names, never a value', async () => {
    const m = await setup();
    expect(m.find('flow-secrets-name-STRIPE_KEY').text()).toBe('STRIPE_KEY');
    expect((m.find('flow-secrets-value').element as HTMLElement & { type: string }).type).toBe('password');
  });

  it('saves a secret, in capitals, and says its value cannot be shown again', async () => {
    mocks.toastSuccess.mockClear();
    const m = await setup([]);
    m.answerBy({ '/api/flow/secrets': [200, ROW] });
    await ionValue(m.find('flow-secrets-name').element, 'stripe_key', 'ionInput');
    await ionValue(m.find('flow-secrets-value').element, 'sk_live_1', 'ionInput');
    await click(m.find('flow-secrets-save').element);
    await settle();
    expect(m.sent().filter((call) => call.path === '/api/flow/secrets').map((call) => call.body)).toEqual([{ name: 'STRIPE_KEY', value: 'sk_live_1' }]);
    expect(mocks.toastSuccess).toHaveBeenCalledWith('STRIPE_KEY saved. Its value can no longer be shown.');
    expect((m.find('flow-secrets-value').element as unknown as { value: string }).value).toBe('');
  });

  it('a refusal shows next to its field and keeps what was typed', async () => {
    const m = await setup([]);
    m.answerBy({ '/api/flow/secrets': [422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { name: 'String should match pattern' } } }] });
    await ionValue(m.find('flow-secrets-name').element, '1BAD', 'ionInput');
    await ionValue(m.find('flow-secrets-value').element, 'v', 'ionInput');
    await click(m.find('flow-secrets-save').element);
    await settle();
    expect(m.find('flow-secrets-problem').text()).toBe('Use capitals, digits and _, starting with a letter (STRIPE_KEY).');
    expect((m.find('flow-secrets-value').element as unknown as { value: string }).value).toBe('v');
  });

  it('deletes one after asking', async () => {
    mocks.confirm.mockResolvedValue(true);
    const m = await setup();
    m.answerBy({ '/api/flow/secrets/delete': [200, { id: 'x1' }] });
    await click(m.find('flow-secrets-delete-STRIPE_KEY').element);
    await settle();
    expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ confirmLabel: 'Yes, delete it' }));
    expect(m.sent().filter((call) => call.path === '/api/flow/secrets/delete').map((call) => call.body)).toEqual([{ name: 'STRIPE_KEY' }]);
  });

  it('without the server\'s key it says so and offers nothing to save', async () => {
    const m = await setup([], false);
    expect(m.find('flow-secrets-unavailable').text()).toBe('This server cannot keep secrets yet: its encryption key is missing.');
    expect(m.find('flow-secrets-save').exists()).toBe(false);
  });
});
