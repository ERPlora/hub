// PAYMENT-F01 and F08: «New method» asks for Name, Type (Bank transfer unless chosen) and Account, with
// «Create method»; a row opens «Editing method — {name}» with «Save», which sends only what changed. A
// name another method has (409) goes under Name, and what was typed stays.
import { describe, expect, it, vi } from 'vitest';

import type { MethodOut } from '../operations';
import { click, ionValue, mountPayment, settle } from '../__tests__/mount-payment';
import MethodFormModal from './MethodFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; helperText?: string };

const BANK: MethodOut = {
  id: 'm1',
  name: 'BBVA account',
  method_type: 'transfer',
  bank_account_ref: '',
  is_active: true,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
};

/** The method as the list shows it (account masked) and as `payment.method.get` gives it (whole). */
const LISTED: MethodOut = { ...BANK, bank_account_ref: 'ES** **** **** **** **** 1332' };
const WHOLE: MethodOut = { ...BANK, bank_account_ref: 'ES91 2100 0418 4502 0005 1332' };

async function setup(
  method: MethodOut | null = null,
  locale: 'en' | 'es' = 'en',
  answers: Record<string, [number, unknown]> = { '/api/payment/methods/detail': [200, WHOLE] },
) {
  const m = await mountPayment(MethodFormModal, { props: { open: false, method }, locale, path: '/payment/methods', answers });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`payment-method-form-${name}`) as Control;
  const save = () => m.inDoc('payment-method-form-submit') as Control;
  return { ...m, field, save };
}

describe('MethodFormModal: New method', () => {
  it('asks for Name, Type and Account, a bank transfer unless chosen', async () => {
    const s = await setup();
    expect(s.inDoc('payment-method-form')?.getAttribute('aria-label')).toBe('New method');
    expect([s.field('name').label, s.field('type').label, s.field('account').label]).toEqual(['Name', 'Type', 'Account']);
    expect(s.field('type').value).toBe('transfer');
    expect([...s.field('type').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'Cash',
      'Bank transfer',
      'Card',
      'SEPA',
      'Cheque',
      'Other',
    ]);
    expect(s.field('account').helperText).toBe('A reference of the bank account, for example the last digits of its IBAN.');
    expect(s.save().textContent).toContain('Create method');
    expect(s.save().disabled).toBe(true);
  });

  it('sends payment.method.create and closes', async () => {
    const s = await setup();
    s.answer(201, { ...BANK, name: 'Cash drawer', method_type: 'cash' });
    await ionValue(s.field('name'), ' Cash drawer ', 'ionInput');
    await ionValue(s.field('type'), 'cash', 'ionChange');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/payment/methods', query: {}, body: { name: 'Cash drawer', method_type: 'cash', bank_account_ref: '' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a name another method has goes under Name, and what was typed stays', async () => {
    const s = await setup();
    const message = 'There is already a payment method with that name. Pick another name.';
    s.answer(409, { error: { code: 'payment.method_exists', message, fields: { name: message } } });
    await ionValue(s.field('name'), 'bbva account', 'ionInput');
    await click(s.save());
    expect(s.field('name').errorText).toBe(message);
    expect(s.field('name').value).toBe('bbva account');
  });
});

describe('MethodFormModal: Editing method — {name}', () => {
  it('is named after the method, loads its whole account (the list masks it) and saves only what changed', async () => {
    const s = await setup(LISTED);
    expect(s.inDoc('payment-method-form')?.getAttribute('aria-label')).toBe('Editing method — BBVA account');
    expect(s.sent()).toEqual([{ method: 'GET', path: '/api/payment/methods/detail', query: { id: 'm1' }, body: undefined }]);
    expect([s.field('name').value, s.field('type').value, s.field('account').value]).toEqual([
      'BBVA account',
      'transfer',
      'ES91 2100 0418 4502 0005 1332',
    ]);
    expect(s.save().textContent).toContain('Save');
    s.answer(200, { ...LISTED, method_type: 'sepa' });
    await ionValue(s.field('type'), 'sepa', 'ionChange');
    await click(s.save());
    // The account it did not touch is not sent back (never the masked text).
    expect(s.sent().slice(1)).toEqual([
      { method: 'POST', path: '/api/payment/methods/update', query: {}, body: { id: 'm1', method_type: 'sepa' } },
    ]);
  });

  it('a method that cannot be read says so and cannot be saved', async () => {
    const message = 'That payment method does not exist in this business.';
    const s = await setup(LISTED, 'en', {
      '/api/payment/methods/detail': [404, { error: { code: 'payment.method_not_found', message } }],
    });
    expect(s.inDoc('payment-method-form-error')?.textContent).toContain(message);
    expect(s.save().disabled).toBe(true);
  });

  it('a reply that is not a method keeps the row’s name, says it could not be read and cannot be saved', async () => {
    const s = await setup(LISTED, 'en', { '/api/payment/methods/detail': [200, {}] });
    expect(s.field('name').value).toBe('BBVA account');
    expect(s.inDoc('payment-method-form-error')?.textContent).toContain('The payment method could not be read.');
    expect(s.save().disabled).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup(LISTED, 'es');
    expect(s.inDoc('payment-method-form')?.getAttribute('aria-label')).toBe('Editando método — BBVA account');
    expect([s.field('name').label, s.field('type').label, s.field('account').label]).toEqual(['Nombre', 'Tipo', 'Cuenta']);
    expect(s.save().textContent).toContain('Guardar');
  });
});
