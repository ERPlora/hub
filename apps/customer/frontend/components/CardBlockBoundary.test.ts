// The frame of another app's block on the card (CUSTOMER-F24, «Si falla: cada bloque enseña su
// propio error»): a block that breaks says so in its place; the card and the other blocks go on.
/* eslint-disable vue/one-component-per-file -- test doubles of other apps' blocks */
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, markRaw } from 'vue';

import { mountCustomer } from '../__tests__/mount-customer';
import CardBlockBoundary from './CardBlockBoundary.vue';

const Fine = defineComponent({ props: { customerId: { type: String, required: true } }, setup: (p) => () => h('p', `visits of ${p.customerId}`) });
const Broken = defineComponent({
  setup() {
    return () => {
      throw new Error('boom');
    };
  },
});

describe('CardBlockBoundary', () => {
  it('shows the block as it is', async () => {
    const m = await mountCustomer(CardBlockBoundary, { props: { block: markRaw(Fine), customerId: 'c1' } });
    expect(m.wrapper.text()).toBe('visits of c1');
  });

  it('a block that breaks says so in its place, and the error does not go up', async () => {
    const warn = vi.spyOn(console, 'error').mockImplementation(() => {});
    const m = await mountCustomer(CardBlockBoundary, { props: { block: markRaw(Broken), customerId: 'c1' } });
    expect(m.wrapper.get('[data-testid="customer-card-block-error"]').text()).toBe('This block could not be shown.');
    warn.mockRestore();
  });
});
