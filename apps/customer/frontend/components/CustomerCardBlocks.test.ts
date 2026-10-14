// What other apps know about the customer, at the end of the card (CUSTOMER-F24): every app that
// offers a block (`apps/<id>/frontend/customer-card/<Block>.vue`, a component taking `customerId`)
// and is on in this business paints it there; Customers only tells it which customer is open.
/* eslint-disable vue/one-component-per-file -- test doubles of other apps' blocks */
import { describe, expect, it, vi } from 'vitest';
import { type Component, defineComponent, h } from 'vue';

import { flush, mountCustomer, OWNER } from '../__tests__/mount-customer';
import CustomerCardBlocks from './CustomerCardBlocks.vue';
import source from './CustomerCardBlocks.vue?raw';

const block = (text: string): Component =>
  defineComponent({ props: { customerId: { type: String, required: true } }, setup: (p) => () => h('p', `${text} ${p.customerId}`) });
const loaders = {
  '../../../appointment/frontend/customer-card/VisitHistory.vue': () => Promise.resolve({ default: block('visits of') }),
  '../../../whatsapp_inbox/frontend/customer-card/Conversations.vue': () => Promise.resolve({ default: block('chats of') }),
  '../../../sale/frontend/customer-card/Broken.vue': () =>
    Promise.resolve({
      default: defineComponent({
        setup: () => () => {
          throw new Error('boom');
        },
      }),
    }),
};

async function setup(apps: { label: string; state: 'on' | 'off' | 'activating' }[]) {
  const m = await mountCustomer(CustomerCardBlocks, { props: { customerId: 'c1', blocks: loaders }, session: { ...OWNER, apps } });
  for (let i = 0; i < 3; i++) await flush();
  return m;
}

describe('CustomerCardBlocks', () => {
  it('paints the block of every app that is on, in the apps\' order, with the customer\'s id only', async () => {
    const m = await setup([
      { label: 'appointment', state: 'on' },
      { label: 'whatsapp_inbox', state: 'on' },
    ]);
    expect(m.wrapper.findAll('[data-testid="customer-card-block"]').map((b) => [b.attributes('data-app'), b.text()])).toEqual([
      ['appointment', 'visits of c1'],
      ['whatsapp_inbox', 'chats of c1'],
    ]);
  });

  it('leaves out the blocks of apps that are off or still activating', async () => {
    const m = await setup([
      { label: 'appointment', state: 'off' },
      { label: 'whatsapp_inbox', state: 'activating' },
    ]);
    expect(m.wrapper.find('[data-testid="customer-card-block"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="customer-card-blocks"]').exists()).toBe(false);
  });

  it('a block that breaks says so in its place; the others go on', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const m = await setup([
      { label: 'appointment', state: 'on' },
      { label: 'sale', state: 'on' },
    ]);
    expect(m.wrapper.text()).toContain('visits of c1');
    expect(m.wrapper.find('[data-testid="customer-card-block-error"]').exists()).toBe(true);
    error.mockRestore();
  });

  it('by default finds the blocks in every app\'s frontend/customer-card folder', () => {
    expect(source).toMatch(/import\.meta\.glob(<[^>]*>)?\(\s*'\.\.\/\.\.\/\.\.\/\*\/frontend\/customer-card\/\*\.vue'/);
  });
});
