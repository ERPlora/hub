// The form of «Call another system» (WORKBOOK FLOW-F27; the old module's flows-f16): method, address (it
// says which permission it will ask for), headers, what to send and how long to wait. Every value is
// text with data, secrets or the call's key inserted ({{…}}); the server's refusals show by field.
import { describe, expect, it } from 'vitest';

import type { Step } from '../operations';
import { click, ionValue, mountFlow } from '../__tests__/mount-flow';
import HttpStepPanel from './HttpStepPanel.vue';
import ValueBox from './ValueBox.vue';

const CALL: Step = { id: 's1', kind: 'http', method: 'POST', url: 'https://api.example.com/v1/orders', headers: { Authorization: 'Bearer {{secret.STRIPE_KEY}}' }, body: '', timeout: 10 };

async function setup(step: Step = CALL, errors: Record<string, string> = {}) {
  const m = await mountFlow(HttpStepPanel, { props: { step, index: 0, steps: [step], catalog: null, errors, pick: async () => 'secret.STRIPE_KEY' }, stubs: { SecretsBox: true } });
  const emitted = () => (m.wrapper.emitted('update:step') ?? []).map(([value]) => value as Step);
  const box = (testid: string) => m.wrapper.findAllComponents(ValueBox).find((candidate) => candidate.props('testid') === testid)!;
  return { ...m, emitted, box };
}

describe('HttpStepPanel', () => {
  it('says which address it will ask permission to call', async () => {
    const s = await setup();
    expect(s.find('flow-http-host-s1').text()).toBe('This step will ask your permission to call api.example.com.');
    const bad = await setup({ ...CALL, url: 'http://api.example.com' });
    expect(bad.find('flow-http-host-s1').text()).toBe('Write it by hand: https:// and the server\'s name first; data only after it.');
  });

  it('changes the method, the address, what it sends and how long it waits', async () => {
    const s = await setup();
    await ionValue(s.find('flow-http-method-s1').element, 'PUT');
    expect(s.emitted().at(-1)).toMatchObject({ method: 'PUT' });
    s.box('flow-http-url-s1').vm.$emit('update:modelValue', 'https://api.example.com/v2/{{input.id}}');
    expect(s.emitted().at(-1)).toMatchObject({ url: 'https://api.example.com/v2/{{input.id}}' });
    s.box('flow-http-body-s1').vm.$emit('update:modelValue', 'input.note');
    expect(s.emitted().at(-1)).toMatchObject({ body: '{{input.note}}' });
    await ionValue(s.find('flow-http-timeout-s1').element, '25', 'ionInput');
    expect(s.emitted().at(-1)).toMatchObject({ timeout: 25 });
    await ionValue(s.find('flow-http-timeout-s1').element, '90', 'ionInput');
    expect(s.emitted().at(-1)).toMatchObject({ timeout: 30 });
  });

  it('adds, fills and removes headers; a secret alone is inserted as text', async () => {
    const s = await setup();
    await click(s.find('flow-http-addheader-s1').element);
    expect(s.emitted().at(-1)).toMatchObject({ headers: { Authorization: 'Bearer {{secret.STRIPE_KEY}}', '': '' } });
    const two = await setup({ ...CALL, headers: { Authorization: 'x', '': '' } });
    await ionValue(two.find('flow-http-header-name-s1-1').element, 'X-Api-Key', 'ionInput');
    expect(two.emitted().at(-1)).toMatchObject({ headers: { Authorization: 'x', 'X-Api-Key': '' } });
    two.box('flow-http-header-value-s1-0').vm.$emit('update:modelValue', 'secret.STRIPE_KEY');
    expect(two.emitted().at(-1)).toMatchObject({ headers: { Authorization: '{{secret.STRIPE_KEY}}', '': '' } });
    await click(two.find('flow-http-unheader-s1-0').element);
    expect(two.emitted().at(-1)).toMatchObject({ headers: { '': '' } });
  });

  it('shows the server\'s refusals next to their field', async () => {
    const s = await setup(CALL, { 'steps.0.url': 'Write the address by hand…', 'steps.0.headers': 'There is no secret called «STRIPE_KEY».' });
    expect(s.box('flow-http-url-s1').props('errorText')).toBe('Write the address by hand…');
    expect(s.find('flow-http-headers-error-s1').text()).toBe('There is no secret called «STRIPE_KEY».');
  });

  it('explains the no-repeat key next to what it sends', async () => {
    const s = await setup();
    expect(s.find('flow-http-keyhint-s1').text()).toContain('the same in every attempt of this call');
  });
});
