// TAX-F07 (change a rate from a date), steps 1–2: «Set end date» on a rule's row opens this
// dialog — what it means, the last day the rule applies (its current end, if any, to begin with) and
// «Save end date». It sends `tax.rule.end` for that rule; a refusal (an end before the start, an
// overlap) stays in the dialog under the date, with the server's words.
import { describe, expect, it, vi } from 'vitest';

import type { RuleOut } from '../operations';
import { click, ionValue, mountTax, settle } from '../__tests__/mount-tax';
import RuleEndModal from './RuleEndModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; type?: string; fill?: string; errorText?: string; disabled?: boolean };

const RULE: RuleOut = {
  id: 'r1',
  country_code: 'ES',
  region_code: null,
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restaurant — food',
  rate_pct: '10.00',
  tax_type: 'vat',
  operation_class: 'subject',
  exempt_reason: null,
  regime_key: null,
  parent_id: null,
  component_label: null,
  valid_from: '2012-09-01',
  valid_to: null,
  is_active: true,
  updated_at: '2026-10-13T10:00:00Z',
};

async function setup(rule: RuleOut = RULE, locale: 'en' | 'es' = 'en') {
  const m = await mountTax(RuleEndModal, { props: { open: false, rule }, locale, path: '/tax/rules' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const date = () => m.inDoc('tax-rule-end-valid_to') as Control;
  const save = () => m.inDoc('tax-rule-end-submit') as Control;
  return { ...m, date, save };
}

describe('RuleEndModal (TAX-F07)', () => {
  it('explains the change of rate and asks for the last day, empty for an open-ended rule', async () => {
    const s = await setup();
    expect(s.inDoc('tax-rule-end')?.getAttribute('aria-label')).toBe('End this tax rule');
    expect(s.inDoc('tax-rule-end-message')?.textContent).toContain('end it the day before the new rate starts');
    expect([s.date().type, s.date().label, s.date().value, s.date().fill, s.date().getAttribute('mode')]).toEqual([
      'date',
      'Last day it applies',
      '',
      'outline',
      'md',
    ]);
    expect([s.save().textContent?.trim(), s.save().disabled]).toEqual(['Save end date', true]);
  });

  it('starts from the end the rule already has', async () => {
    const s = await setup({ ...RULE, valid_to: '2026-12-31' });
    expect(s.date().value).toBe('2026-12-31');
  });

  it('sends tax.rule.end for that rule with the day, then closes', async () => {
    const s = await setup();
    s.answer(200, { ...RULE, valid_to: '2026-12-31' });
    await ionValue(s.date(), '2026-12-31', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/tax/rules/end', query: {}, body: { id: 'r1', valid_to: '2026-12-31' } }]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an end before the start (409) is said under the date and the dialog stays open', async () => {
    const s = await setup();
    const message = 'That rule cannot end before the day it starts.';
    s.answer(409, { error: { code: 'tax.rule_end_invalid', message, fields: { valid_to: message } } });
    await ionValue(s.date(), '2000-01-01', 'ionInput');
    await click(s.save());
    expect(s.date().errorText).toBe(message);
    expect(s.date().classList.contains('ion-invalid')).toBe(true);
    expect(s.inDoc('tax-rule-end-error')?.textContent).toContain(message);
    expect(s.wrapper.emitted('update:open')?.at(-1)).not.toEqual([false]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(RULE, 'es');
    expect(s.inDoc('tax-rule-end')?.getAttribute('aria-label')).toBe('Fecha de fin de la regla');
    expect(s.date().label).toBe('Último día en que se aplica');
    expect(s.save().textContent?.trim()).toBe('Guardar fecha de fin');
  });
});
