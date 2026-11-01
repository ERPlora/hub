// The form of «Send a message» (WORKBOOK FLOW-F31; the old module's flows-f15): to whom — a datum, the customer's
// exact international number —, the message sent as it is within the customer's 24 hours, and the approved
// template (with a value for each of its blanks) WhatsApp lets through after them. The templates are the
// business's approved ones the inbox can fill, read live from the WhatsApp inbox, with their loading, empty and
// error states. A template with a photo, a video or a document at the top goes with a file (FLOW-F32; the old hub's
// HUB-F112): its own, or the one chosen in the step, kept at once in the business's files.
import { describe, expect, it } from 'vitest';

import type { Step } from '../operations';
import { errorFrame, flush, ionValue, mountFlow, resultFrame, settle } from '../__tests__/mount-flow';
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
  expect(s.params(TEMPLATE_LIST)).toEqual([{ fillable: true, limit: 100 }]);
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

// ── A photo, a video or a document at the top (FLOW-F32) ────────────────────────────────────────────────────────────

const MEDIA = '/p/media/0193a5b2c3d47e8f9a0b1c2d3e4f5a6b/whatsapp_inbox/samples';
const OWN = { id: 'f1', header_format: 'IMAGE', content_type: 'image/jpeg', size: 6349, name: 'carta.jpg', url: `${MEDIA}/0123456789abcdef.jpg` };
const CHOSEN = { id: 'f9', header_format: 'VIDEO', content_type: 'video/mp4', size: 2 * 1024 * 1024, name: 'promo.mp4', url: `${MEDIA}/fedcba9876543210.mp4` };
const WITH_FILES = {
  rows: [
    { id: 't3', name: 'carta_foto', language: 'es', category: 'MARKETING', status: 'APPROVED', body: 'La carta de hoy', variables: 0, header_format: 'IMAGE', header_sample: OWN },
    { id: 't4', name: 'promo_video', language: 'es', category: 'MARKETING', status: 'APPROVED', body: '¡Oferta {{1}}!', variables: 1, header_format: 'VIDEO', header_sample: null },
    { id: 't5', name: 'aviso', language: 'es', category: 'UTILITY', status: 'APPROVED', body: 'Aviso', variables: 0, header_format: 'TEXT', header_sample: null },
  ],
  total: 3,
  limit: 100,
  offset: 0,
};
const UPLOAD = '/api/whatsapp_inbox/templates/samples';
const DETAIL = '/api/whatsapp_inbox/templates/samples/detail';
const chosenStep = (template: Record<string, unknown>): Step => ({ ...STEP, params: { phone: '', text: '', template } });
const withFiles = (step: Step = STEP) => withTemplates(step, (id) => resultFrame(id, WITH_FILES, 1));
const video = (name = 'promo.mp4', type = 'video/mp4', size = 8) => new File([new Uint8Array(size)], name, { type });

async function pickFile(s: Awaited<ReturnType<typeof setup>>, file: File): Promise<void> {
  const input = s.find('flow-message-file-input-s2').element as HTMLInputElement;
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new Event('change'));
  await flush();
  await settle();
}

describe('MessageStepPanel: a file at the top of the template (FLOW-F32)', () => {
  it('a template with a photo of its own goes with it, said with what WhatsApp takes, and it may be changed', async () => {
    const s = await withFiles(chosenStep({ name: 'carta_foto', language: 'es', variables: [] }));
    expect(s.find('flow-message-file-name-s2').text()).toBe('Photo: carta.jpg · 6.2 KB');
    expect(s.find('flow-message-file-rules-s2').text()).toBe('JPEG or PNG, up to 5 MB. The customer gets the template with this file at the top.');
    expect(s.find('flow-message-file-choose-s2').text()).toBe('Change file');
    expect(s.find('flow-message-file-input-s2').attributes('accept')).toBe('image/jpeg,image/png');
    expect(s.find('flow-message-file-missing-s2').exists()).toBe(false);
  });

  it('one without a file of its own asks for it; the file picked is kept at once and the step sends it', async () => {
    const s = await withFiles(chosenStep({ name: 'promo_video', language: 'es', variables: [''] }));
    expect(s.find('flow-message-file-empty-s2').text()).toBe('No file chosen');
    expect(s.find('flow-message-file-missing-s2').text()).toBe('This template goes with a video at the top: choose it, or WhatsApp will not send it.');
    expect(s.find('flow-message-file-choose-s2').text()).toBe('Choose file');
    expect(s.find('flow-message-file-input-s2').attributes('accept')).toBe('video/mp4');

    s.answerBy({ [UPLOAD]: [201, CHOSEN] });
    await pickFile(s, video());
    expect(s.sent().at(-1)).toMatchObject({ method: 'POST', path: UPLOAD, body: { header_format: 'VIDEO', name: 'promo.mp4', content_base64: 'AAAAAAAAAAA=' } });
    expect(s.emitted().at(-1)!.params.template).toEqual({ name: 'promo_video', language: 'es', variables: [''], header_sample: 'f9' });
  });

  it('the file a step keeps is read by its id and named; changing the template lets it go', async () => {
    const s = await mountFlow(MessageStepPanel, {
      props: { step: chosenStep({ name: 'promo_video', language: 'es', variables: ['x'], header_sample: 'f9' }), index: 1, steps: [STEP], catalog: null, errors: {}, pick: async () => null },
      answers: { [DETAIL]: [200, CHOSEN] },
    });
    const stream = await s.live();
    stream.push(resultFrame(s.subId(TEMPLATE_LIST), WITH_FILES, 1));
    await settle();
    expect(s.sent().find((call) => call.path === DETAIL)?.query).toEqual({ id: 'f9' });
    expect(s.find('flow-message-file-name-s2').text()).toBe('Video: promo.mp4 · 2 MB');
    expect(s.find('flow-message-file-choose-s2').text()).toBe('Change file');

    await ionValue(s.find('flow-message-template-s2').element, 'aviso|es');
    const params = ((s.wrapper.emitted('update:step') ?? []).at(-1)![0] as Step & { params: Record<string, unknown> }).params;
    expect(params.template).toEqual({ name: 'aviso', language: 'es', variables: [] });
  });

  it('a file a step kept that is no longer there is said, and another may be chosen', async () => {
    const s = await mountFlow(MessageStepPanel, {
      props: { step: chosenStep({ name: 'promo_video', language: 'es', variables: ['x'], header_sample: 'gone' }), index: 1, steps: [STEP], catalog: null, errors: {}, pick: async () => null },
      answers: { [DETAIL]: [404, { error: { code: 'whatsapp_inbox.sample_not_found', message: 'That file is not among this business’s files.' } }] },
    });
    const stream = await s.live();
    stream.push(resultFrame(s.subId(TEMPLATE_LIST), WITH_FILES, 1));
    await settle();
    expect(s.find('flow-message-file-gone-s2').text()).toBe('The file this step had chosen is no longer kept: choose it again.');
    expect(s.find('flow-message-file-choose-s2').text()).toBe('Choose file');
  });

  it('a file it cannot read now says so and offers to try again', async () => {
    const step = chosenStep({ name: 'promo_video', language: 'es', variables: ['x'], header_sample: 'f9' });
    const s = await mountFlow(MessageStepPanel, {
      props: { step, index: 1, steps: [step], catalog: null, errors: {}, pick: async () => null },
      answers: { [DETAIL]: [500, { error: { code: 'internal_error', message: 'Something went wrong.' } }] },
    });
    const stream = await s.live();
    stream.push(resultFrame(s.subId(TEMPLATE_LIST), WITH_FILES, 1));
    await settle();
    expect(s.find('flow-message-file-readerror-s2').text()).toContain('The file of this step could not be read.');
    expect(s.find('flow-message-file-missing-s2').exists()).toBe(false);
    s.answerBy({ [DETAIL]: [200, CHOSEN] });
    await s.find('flow-message-file-retry-s2').trigger('click');
    await flush();
    await settle();
    expect(s.find('flow-message-file-readerror-s2').exists()).toBe(false);
    expect(s.find('flow-message-file-name-s2').text()).toBe('Video: promo.mp4 · 2 MB');
  });

  it('a file of another kind or too heavy is said under it and never uploaded; a refusal of the upload too', async () => {
    const s = await withFiles(chosenStep({ name: 'promo_video', language: 'es', variables: [''] }));
    const before = s.sent().length;
    await pickFile(s, video('carta.pdf', 'application/pdf'));
    expect(s.find('flow-message-file-error-s2').text()).toBe('Choose an MP4 video.');
    await pickFile(s, video('long.mp4', 'video/mp4', 16 * 1024 * 1024 + 1));
    expect(s.find('flow-message-file-error-s2').text()).toBe('This file weighs more than 16 MB: choose a lighter one.');
    expect(s.sent().length).toBe(before);

    s.answerBy({ [UPLOAD]: [422, { error: { code: 'invalid_payload', message: 'Invalid', fields: { content_base64: 'That is not an MP4 video.' } } }] });
    await pickFile(s, video());
    expect(s.find('flow-message-file-error-s2').text()).toBe('That is not an MP4 video.');
    expect(s.emitted().some((step) => (step.params.template as Record<string, unknown> | undefined)?.header_sample)).toBe(false);
  });

  it('a text header asks for no file', async () => {
    const s = await withFiles(chosenStep({ name: 'aviso', language: 'es', variables: [] }));
    expect(s.find('flow-message-file-s2').exists()).toBe(false);
  });

  it('says it all in Spanish', async () => {
    const step = chosenStep({ name: 'promo_video', language: 'es', variables: [''] });
    const s = await mountFlow(MessageStepPanel, { props: { step, index: 1, steps: [step], catalog: null, errors: {}, pick: async () => null }, locale: 'es' });
    const stream = await s.live();
    stream.push(resultFrame(s.subId(TEMPLATE_LIST), WITH_FILES, 1));
    await settle();
    expect(s.find('flow-message-file-empty-s2').text()).toBe('Ningún archivo elegido');
    expect(s.find('flow-message-file-missing-s2').text()).toBe('Esta plantilla lleva un vídeo arriba: elígelo o WhatsApp no la enviará.');
    expect(s.find('flow-message-file-rules-s2').text()).toBe('MP4, hasta 16 MB. El cliente recibe la plantilla con este archivo arriba.');
    expect(s.find('flow-message-file-choose-s2').text()).toBe('Elegir archivo');
  });
});

describe('MessageStepPanel: the file at the top after changing the template (FLOW-F32)', () => {
  it('a template chosen after one whose file was gone shows its own file, with no «gone» left over', async () => {
    const gone = chosenStep({ name: 'promo_video', language: 'es', variables: ['x'], header_sample: 'gone' });
    const s = await mountFlow(MessageStepPanel, {
      props: { step: gone, index: 1, steps: [gone], catalog: null, errors: {}, pick: async () => null },
      answers: { [DETAIL]: [404, { error: { code: 'whatsapp_inbox.sample_not_found', message: 'That file is not among this business’s files.' } }] },
    });
    const stream = await s.live();
    stream.push(resultFrame(s.subId(TEMPLATE_LIST), WITH_FILES, 1));
    await settle();
    expect(s.find('flow-message-file-gone-s2').exists()).toBe(true);

    await ionValue(s.find('flow-message-template-s2').element, 'carta_foto|es');
    const next = (s.wrapper.emitted('update:step') ?? []).at(-1)![0] as Step;
    await s.wrapper.setProps({ step: next, steps: [next] });
    await settle();
    expect(s.find('flow-message-file-name-s2').text()).toBe('Photo: carta.jpg · 6.2 KB');
    expect(s.find('flow-message-file-gone-s2').exists()).toBe(false);
    expect(s.find('flow-message-file-readerror-s2').exists()).toBe(false);
  });
});
