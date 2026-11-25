import { describe, expect, it } from 'vitest';

import { mountBase } from '../__tests__/mount-base';
import RolePhrase from './RolePhrase.vue';

describe('RolePhrase', () => {
  it('is the phrase of the permission, which wraps', async () => {
    const m = await mountBase(RolePhrase, { props: { phrase: 'Cobrar', review: false } });
    expect(m.wrapper.text()).toBe('Cobrar');
    expect(m.wrapper.classes()).toContain('ion-text-wrap');
  });

  it('is marked while the permission is left to review', async () => {
    const m = await mountBase(RolePhrase, { locale: 'es', props: { phrase: 'Cobrar', review: true } });
    expect(m.wrapper.get('[data-testid="role-to-review"]').text()).toBe('Por revisar');
  });
});
