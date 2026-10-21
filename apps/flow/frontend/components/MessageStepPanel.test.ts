// The form of «Send a message» (WORKBOOK FLOW-F31; the old module's flows-f15): to whom — a datum, the customer's
// exact international number —, the message sent as it is within the customer's 24 hours, and the approved
// template (with a value for each of its blanks) WhatsApp lets through after them. The templates are the
// business's approved ones, read live from the WhatsApp inbox, with their loading, empty and error states.
import { describe, expect, it } from 'vitest';

import type { Step } from '../operations';
import { errorFrame, ionValue, mountFlow, resultFrame, settle } from '../__tests__/mount-flow';
import MessageStepPanel from './MessageStepPanel.vue';
import ValueBox from './ValueBox.vue';

const NOTIFY = 'whatsapp_inbox.message.notify';
const STEP: Step = { id: 's2', kind: 'command', operation: NOTIFY, params: { phone: '', text: '' } };
const TEMPLATES = {
  rows: [
    { id: 't1', name: 'appointment_confirmed', language: 'es', category: 'UTILITY', status: 'APPROVED', body: 'Confirmada: {{1}} a las {{2}}.', variables: 2 },
    { id: 't2', name: 'promo', language: 'es', category: 'MARKETING', status: 'APPROVED', body: '¡Oferta!', variables: 0 },
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

async function setup(step: Step = STEP, errors: Record<string, string> = {}) {
  const m = await mountFlow(MessageStepPanel, { props: { step, index: 1, steps: [step], catalog: null, errors, pick: async () => 'steps.s1.phone' } });
  const emitted = () => (m.wrapper.emitted('update:step') ?? []).map(([value]) => value as Step & { params: Record<string, unknown> });
  const box = (testid: string) => m.wrapper.findAllComponents(ValueBox).find((candidate) => candidate.props('testid') === testid);
  return { ...m, emitted, box };
}

const TEMPLATE_LIST = 'whatsapp_inbox.template.list';

async function withTemplates(step: Step = STEP, frame = (id: string) => resultFrame(id, TEMPLATES, 1)) {
  const s = await setup(step);
  const stream = await s.live();
  expect(s.params(TEMPLATE_LIST)).toEqual([{ sendable: true, limit: 100 }]);
  stream.push(frame(s.subId(TEMPLATE_LIST)));
  await settle();
  return s;
}

describe('MessageStepPanel', () => {
  it('writes to the number a datum gives, never one typed by hand, and says so', async () => {
    const s = await setup();
    expect(s.box('flow-message-phone-s2')!.props()).toMatchObject({ required: true, label: 'To (their phone)' });
    expect(s.find('flow-message-phonehint-s2').text()).toBe(
      'Insert the customer\'s phone: only the WhatsApp conversation of exactly that international number gets it. If there is none, nothing is sent.',
    );
    s.box('flow-message-phone-s2')!.vm.$emit('update:modelValue', 'steps.s1.phone');
    expect(s.emitted().at(-1)!.params).toEqual({ phone: 'steps.s1.phone', text: '' });
  });

  it('the message goes as it is within the customer\'s 24 hours, its data written in', async () => {
    const s = await setup();
    expect(s.find('flow-message-texthint-s2').text()).toBe('Sent as it is if the customer wrote to you in the last 24 hours.');
    s.box('flow-message-text-s2')!.vm.$emit('update:modelValue', 'steps.s1.name');
    expect(s.emitted().at(-1)!.params).toEqual({ phone: '', text: '{{steps.s1.name}}' });
  });

  it('after the 24 hours, an approved template with a value for each blank', async () => {
    const s = await withTemplates();
    expect(s.find('flow-message-templatehint-s2').text()).toBe('After 24 hours WhatsApp only lets an approved template through.');
    await ionValue(s.find('flow-message-template-s2').element, 'appointment_confirmed|es');
    expect(s.emitted().at(-1)!.params).toEqual({ phone: '', text: '', template: { name: 'appointment_confirmed', language: 'es', variables: ['', ''] } });

    const chosen: Step = { ...STEP, params: { phone: '', text: '', template: { name: 'appointment_confirmed', language: 'es', variables: ['', ''] } } };
    const again = await withTemplates(chosen);
    expect(again.find('flow-message-preview-s2').text()).toBe('Confirmada: {{1}} a las {{2}}.');
    again.box('flow-message-var-s2-1')!.vm.$emit('update:modelValue', 'steps.s1.start_time_label');
    expect(again.emitted().at(-1)!.params.template).toEqual({ name: 'appointment_confirmed', language: 'es', variables: ['', '{{steps.s1.start_time_label}}'] });
    await ionValue(again.find('flow-message-template-s2').element, '');
    expect(again.emitted().at(-1)!.params).toEqual({ phone: '', text: '' });
  });

  it('a template it no longer finds stays chosen and says so', async () => {
    const gone: Step = { ...STEP, params: { phone: '', template: { name: 'old_one', language: 'es', variables: ['x'] } } };
    const s = await withTemplates(gone);
    expect(s.find('flow-message-missing-s2').text()).toBe('«old_one» is not among your approved WhatsApp templates: WhatsApp will not send it.');
    expect(s.box('flow-message-var-s2-0')!.props('modelValue')).toBe('x');
  });

  it('without approved templates it says where to make one', async () => {
    const s = await withTemplates(STEP, (id) => resultFrame(id, { rows: [], total: 0, limit: 100, offset: 0 }, 1));
    expect(s.find('flow-message-notemplates-s2').text()).toBe('You have no approved templates yet: create one in WhatsApp › Settings.');
  });

  it('when the templates cannot be read it says so and offers to try again', async () => {
    const s = await withTemplates(STEP, (id) => errorFrame(id, 'internal_error'));
    expect(s.find('flow-message-templateerror-s2').text()).toContain('Your WhatsApp templates could not be read.');
  });

  it('shows the server\'s refusals next to their field', async () => {
    const s = await setup(STEP, { 'steps.1.params.phone': 'Field required', 'steps.1.params.text': 'Write a message or choose a template.' });
    expect(s.box('flow-message-phone-s2')!.props('errorText')).toBe('Field required');
    expect(s.box('flow-message-text-s2')!.props('errorText')).toBe('Write a message or choose a template.');
  });
});
