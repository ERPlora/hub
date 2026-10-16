// The customer card (WORKBOOK «Ficha de cliente»; CUSTOMER-F03–F07, F13–F16, F19, F23, F24): the
// name and the buttons the profile allows — Edit, Delete, Merge with…, Erase personal data —; the
// data (or, editing, the form with the custom fields and «Active»); Groups and Tags; Marketing
// consent; Add note and Activity; Purchases; Linked orders; and the other apps' blocks. Live: what
// another person changes shows without reloading; a card gone says «no longer available».
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DETAIL } from '../__tests__/fixtures';
import {
  BYE,
  EMPLOYEE,
  errorFrame,
  flush,
  json,
  MANAGER,
  type MountOptions,
  mountCustomer,
  refusal,
  sent,
  subId,
  VIEWER,
} from '../__tests__/mount-customer';
import ActivityPanel from '../components/ActivityPanel.vue';
import ConsentPanel from '../components/ConsentPanel.vue';
import HealthPanel from '../components/HealthPanel.vue';
import CustomerCardBlocks from '../components/CustomerCardBlocks.vue';
import CustomerDeleteDialog from '../components/CustomerDeleteDialog.vue';
import CustomerFacts from '../components/CustomerFacts.vue';
import CustomerForm from '../components/CustomerForm.vue';
import ErasePanel from '../components/ErasePanel.vue';
import LinkedOrders from '../components/LinkedOrders.vue';
import MembershipEditor from '../components/MembershipEditor.vue';
import MergePanel from '../components/MergePanel.vue';
import PurchaseHistory from '../components/PurchaseHistory.vue';
import CustomerDetailPage from './CustomerDetailPage.vue';
import source from './CustomerDetailPage.vue?raw';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());
afterEach(() => {
  document.body.innerHTML = '';
});

const CARD = 'customer.customer.detail';

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(CustomerDetailPage, { props: { id: 'c1' }, path: '/customer/customers/c1', attachTo: document.body, ...options });
  const call = await m.live();
  const show = (card: unknown, rev = 1) => m.result(call, CARD, card, rev);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const click = async (id: string) => {
    await m.wrapper.get(`[data-testid="${id}"]`).trigger('click');
    await flush();
  };
  return { ...m, call, show, testid, click };
}

describe('CustomerDetailPage: the card, live', () => {
  it('follows customer.customer.detail of its id, with a spinner until the first result', async () => {
    const s = await setup();
    expect(s.params(CARD)).toEqual([{ id: 'c1' }]);
    expect(s.testid('customer-detail-loading').exists()).toBe(true);
    await s.show(DETAIL);
    expect(s.testid('customer-detail-loading').exists()).toBe(false);
    const page = s.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('backHref'), page.props('contentLayout')]).toEqual([
      'Ana García',
      '/customer/customers',
      'detail',
    ]);
    expect((page.props('tabs') as { id: string }[]).map((t) => t.id)).toEqual(['customers', 'groups', 'tags', 'fields']);
    expect(s.wrapper.findComponent(CustomerFacts).props('customer')).toEqual(DETAIL);
  });

  it('lays out the card in the product order: data, health, groups and tags, consent, note and activity, purchases, orders, other apps', async () => {
    const s = await setup();
    await s.show(DETAIL);
    const order = [CustomerFacts, HealthPanel, MembershipEditor, ConsentPanel, ActivityPanel, PurchaseHistory, LinkedOrders, CustomerCardBlocks].map(
      (c) => s.wrapper.findComponent(c as never).element,
    );
    for (let i = 1; i < order.length; i++) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING, `section ${i}`).toBeTruthy();
    }
    expect(s.wrapper.findAllComponents(MembershipEditor).map((m) => [m.props('kind'), m.props('selected')])).toEqual([
      ['groups', DETAIL.group_ids],
      ['tags', DETAIL.tag_ids],
    ]);
    expect(s.wrapper.findComponent(ConsentPanel).props()).toMatchObject({ customerId: 'c1', consent: DETAIL.consent, editable: true });
    expect(s.wrapper.findComponent(CustomerCardBlocks).props('customerId')).toBe('c1');
    // CUSTOMER-F32: the allergies right after the data, where whoever does the service looks first.
    expect(s.wrapper.findComponent(HealthPanel).props()).toMatchObject({ customerId: 'c1', editable: true });
  });

  it('opens one stream: the blocks follow the card id from the start, hidden until the card arrives', async () => {
    const s = await setup();
    // Mounted only after the first result, the blocks made the SDK abort that stream and open another.
    const blocks = [
      'customer.health.detail',
      'customer.group.list',
      'customer.tag.list',
      'customer.consent.history',
      'customer.activity.list',
      'customer.purchase.list',
      'customer.order.list',
    ] as const;
    expect(blocks.filter((op) => s.params(op).length === 0)).toEqual([]);
    expect((s.testid('customer-detail-blocks').element as HTMLElement).style.display).toBe('none');
    await s.show(DETAIL);
    await s.clock.advance(150);
    expect(s.net.streams).toHaveLength(1);
    expect(s.call.aborted()).toBe(false);
    expect((s.testid('customer-detail-blocks').element as HTMLElement).style.display).toBe('');
  });

  it('a card that is gone, or an app that is off, follows none of its blocks', async () => {
    const s = await setup();
    await s.show(DETAIL);
    s.call.push(errorFrame(subId(s.client, CARD), 'customer.customer_unavailable'));
    await flush();
    expect(s.testid('customer-detail-blocks').exists()).toBe(false);
    expect(s.wrapper.findComponent(HealthPanel).exists()).toBe(false);
    const off = await setup();
    off.call.push(errorFrame(subId(off.client, CARD), 'app_inactive'));
    await flush();
    expect(off.testid('customer-detail-blocks').exists()).toBe(false);
  });

  it('a change made elsewhere shows without reloading', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.show({ ...DETAIL, name: 'Ana García López' }, 2);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Ana García López');
  });

  it('a card deleted, merged or erased says «This customer is no longer available.»', async () => {
    const s = await setup();
    await s.show(DETAIL);
    s.call.push(errorFrame(subId(s.client, CARD), 'customer.customer_unavailable'));
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'customer-detail-gone')!;
    expect(banner.props('heading')).toBe('This customer is no longer available.');
    expect(s.wrapper.findComponent(CustomerFacts).exists()).toBe(false);
    expect(s.testid('customer-detail-actions').exists()).toBe(false);
  });

  it('another failure says the card could not be loaded, with the reason', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, CARD), 'boom'));
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'customer-detail-error')!;
    expect(banner.props('heading')).toBe('The customer could not be loaded');
    expect(banner.text()).toContain('msg boom');
  });

  it('says when the app is not active; keeps the card while reconnecting', async () => {
    const s = await setup();
    await s.show(DETAIL);
    s.call.push(BYE);
    await flush();
    expect(s.testid('customer-detail-reconnecting').text()).toBe('Reconnecting…');
    expect(s.wrapper.findComponent(CustomerFacts).exists()).toBe(true);
    const off = await setup();
    off.call.push(errorFrame(subId(off.client, CARD), 'app_inactive'));
    await flush();
    expect(off.wrapper.findAllComponents(InlineFeedback).some((b) => b.props('heading') === 'This app is not active in this business')).toBe(true);
  });
});

describe('CustomerDetailPage: the buttons the profile allows', () => {
  const buttons = (s: Awaited<ReturnType<typeof setup>>) =>
    s.wrapper.findAll('[data-testid="customer-detail-actions"] ion-button').map((b) => b.attributes('data-testid'));

  it('owner: Edit, Delete, Merge with… and Erase personal data', async () => {
    const s = await setup();
    await s.show(DETAIL);
    expect(buttons(s)).toEqual(['customer-detail-edit', 'customer-detail-delete', 'customer-detail-merge', 'customer-detail-erase']);
    expect(s.wrapper.findAll('[data-testid="customer-detail-actions"] ion-button').map((b) => b.text())).toEqual([
      'Edit',
      'Delete',
      'Merge with…',
      'Erase personal data',
    ]);
  });

  it('manager: Edit and Merge with…; employee: Edit only; who only views: none, and read-only sections', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(DETAIL);
    expect(buttons(manager)).toEqual(['customer-detail-edit', 'customer-detail-merge']);
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(DETAIL);
    expect(buttons(employee)).toEqual(['customer-detail-edit']);
    const viewer = await setup({ session: VIEWER });
    await viewer.show(DETAIL);
    expect(buttons(viewer)).toEqual([]);
    expect(viewer.wrapper.findAllComponents(MembershipEditor).every((m) => m.props('editable') === false)).toBe(true);
    expect(viewer.wrapper.findComponent(ConsentPanel).props('editable')).toBe(false);
    expect(viewer.wrapper.findComponent(HealthPanel).props('editable')).toBe(false);
    expect(viewer.wrapper.findComponent(ActivityPanel).props('canAddNote')).toBe(false);
  });

  it('«Delete» asks in its dialog; deleted, back to the list', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-delete');
    expect(s.wrapper.findComponent(CustomerDeleteDialog).props('customer')).toEqual({ id: 'c1', name: 'Ana García' });
    s.wrapper.findComponent(CustomerDeleteDialog).vm.$emit('deleted', 'c1');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/customer/customers');
  });

  it('«Merge with…» opens its panel on the card; done, it closes', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-merge');
    expect(s.wrapper.findComponent(MergePanel).props('customer')).toEqual({ id: 'c1', name: 'Ana García' });
    s.wrapper.findComponent(MergePanel).vm.$emit('done');
    await flush();
    expect(s.wrapper.findComponent(MergePanel).exists()).toBe(false);
  });

  it('«Erase personal data» opens its panel (one panel at a time); erased, back to the list', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-merge');
    await s.click('customer-detail-erase');
    expect(s.wrapper.findComponent(MergePanel).exists()).toBe(false);
    expect(s.wrapper.findComponent(ErasePanel).exists()).toBe(true);
    s.wrapper.findComponent(ErasePanel).vm.$emit('erased');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/customer/customers');
  });
});

describe('CustomerDetailPage: «Edit» (F04)', () => {
  it('turns the data into the form with the custom fields, as saved', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-edit');
    const form = s.wrapper.findComponent(CustomerForm);
    expect(form.props('mode')).toBe('edit');
    expect(form.props('modelValue')).toMatchObject({ name: 'Ana García', phone: '+34600111222', birthday: '1990-02-03', anniversary: '' });
    expect(form.props('customFields')).toEqual(DETAIL.custom_fields);
    expect(form.props('fieldValues')).toEqual({ f1: 'Nuts', f2: 'true', f3: '' });
    expect(s.wrapper.findComponent(CustomerFacts).exists()).toBe(false);
    expect(s.testid('customer-detail-edit').exists()).toBe(false);
  });

  it('«Save» sends what changed and every custom field in one call; then «Customer updated» and the data again', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-edit');
    const form = s.wrapper.findComponent(CustomerForm);
    form.vm.$emit('update:modelValue', { ...form.props('modelValue'), city: 'Sevilla' });
    form.vm.$emit('update:fieldValues', { f1: '', f2: 'false', f3: 'A' });
    await flush();
    s.net.onApi(() => json({ ...DETAIL, city: 'Sevilla' }));
    await s.wrapper.get('[data-testid="customer-edit-form"]').trigger('submit');
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({
      path: '/api/customer/customers/update',
      body: {
        id: 'c1',
        city: 'Sevilla',
        field_values: [
          { field_id: 'f1', value: '' },
          { field_id: 'f2', value: 'false' },
          { field_id: 'f3', value: 'A' },
        ],
      },
    });
    expect((sent(s.net.api[0]).body as Record<string, unknown>).name).toBeUndefined();
    expect(toastSuccess).toHaveBeenCalledWith('Customer updated');
    expect(s.wrapper.findComponent(CustomerForm).exists()).toBe(false);
  });

  it('a refusal keeps the form with what was typed and the reasons under their fields', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-edit');
    s.net.onApi(() => refusal(422, 'customer.field_required', 'This field is required.', { 'field_values.f1': 'This field is required.' }));
    await s.wrapper.get('[data-testid="customer-edit-form"]').trigger('submit');
    await flush();
    expect(s.wrapper.findComponent(CustomerForm).props('errors')).toEqual({ 'field_values.f1': 'This field is required.' });
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('«Save» waits for a name; «Cancel» goes back to the data without saving', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-edit');
    const form = s.wrapper.findComponent(CustomerForm);
    form.vm.$emit('update:modelValue', { ...form.props('modelValue'), name: '  ' });
    await flush();
    expect((s.wrapper.get('[data-testid="customer-edit-save"]').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    await s.click('customer-edit-cancel');
    expect(s.wrapper.findComponent(CustomerFacts).exists()).toBe(true);
    expect(s.net.api).toHaveLength(0);
  });

  it('a result that arrives while editing does not overwrite the form', async () => {
    const s = await setup();
    await s.show(DETAIL);
    await s.click('customer-detail-edit');
    const form = s.wrapper.findComponent(CustomerForm);
    form.vm.$emit('update:modelValue', { ...form.props('modelValue'), city: 'Mine' });
    await flush();
    await s.show({ ...DETAIL, city: 'Theirs' }, 2);
    expect(s.wrapper.findComponent(CustomerForm).props('modelValue')).toMatchObject({ city: 'Mine' });
  });
});

describe('CustomerDetailPage: language and markup', () => {
  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(DETAIL);
    expect(s.wrapper.findAll('[data-testid="customer-detail-actions"] ion-button').map((b) => b.text())).toEqual([
      'Editar',
      'Eliminar',
      'Fusionar con…',
      'Borrar datos personales',
    ]);
  });

  it('has no OutfitKit tag and formats nothing by hand', () => {
    expect(source).not.toMatch(/<ok[-]/);
    expect(source).not.toMatch(/Intl\.|toLocale|toFixed|new Date\(/);
  });
});
