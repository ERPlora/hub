// The «Name» of the printing app's windows (a printer, PRINTING-F03; a device, PRINTING-F18): up to the 100 characters
// the server keeps, in an outlined md box under its host's label, handed back as text, with its window's refusal under
// it, red. What the host puts on it — its hook and its name in the form, by which the window tells which refused field
// a person corrected — lands on the field.
import { describe, expect, it } from 'vitest';

import { ionValue, mountPrinting } from '../__tests__/mount-printing';
import PrintingNameField from './PrintingNameField.vue';

type Control = HTMLElement & {
  label?: string;
  placeholder?: string;
  value?: unknown;
  maxlength?: unknown;
  fill?: string;
  labelPlacement?: string;
  errorText?: string;
  name?: string;
};

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountPrinting(PrintingNameField, {
    props: { modelValue: 'Till', label: 'Name', 'data-testid': 'printing-thing-name', name: 'name', ...props },
  });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: string) => m.wrapper.setProps({ modelValue: value }) });
  return { ...m, field: () => m.wrapper.element as Control };
}

describe('PrintingNameField', () => {
  it('is an outlined md box of up to 100 characters, under its host’s label, with the hook and name its host gives', async () => {
    const field = (await setup()).field();
    expect([
      field.tagName,
      field.label,
      field.fill,
      field.getAttribute('mode'),
      field.labelPlacement,
      Number(field.maxlength),
      field.value,
      field.name,
      field.dataset.testid,
    ]).toEqual(['ION-INPUT', 'Name', 'outline', 'md', 'stacked', 100, 'Till', 'name', 'printing-thing-name']);
  });

  it('shows the example its host gives, and none without one', async () => {
    expect((await setup({ placeholder: 'Counter till' })).field().placeholder).toBe('Counter till');
    expect((await setup()).field().placeholder ?? '').toBe('');
  });

  it('hands what is typed back to its host as text', async () => {
    const s = await setup();
    await ionValue(s.field(), 'Kitchen', 'ionInput');
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['Kitchen']);
  });

  it('says its window’s refusal under it, red, and nothing without one', async () => {
    const refused = (await setup({ errorText: 'Give it a name.' })).field();
    expect([refused.errorText, refused.classList.contains('ion-invalid'), refused.classList.contains('ion-touched')]).toEqual([
      'Give it a name.',
      true,
      true,
    ]);
    const fine = (await setup()).field();
    expect([fine.errorText ?? '', fine.classList.contains('ion-invalid'), fine.classList.contains('ion-touched')]).toEqual([
      '',
      false,
      false,
    ]);
  });
});
