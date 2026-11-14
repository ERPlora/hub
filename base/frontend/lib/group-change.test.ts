// FormModal takes a refusal away when it hears the field of that name change. A refusal about a group of controls
// (a rule's tiers, a schedule's week, the customer chosen in her own search) has no field of its name: the group's
// `<fieldset name="<key>">` (or the FieldGroup that paints one) says each change the person makes to it, and only that
// refusal goes.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import { type Component, defineComponent, h, nextTick } from 'vue';

import { flush, mountBase } from '../__tests__/mount-base';
import FieldGroup from '../components/FieldGroup.vue';
import { useGroupChange } from './group-change';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const RISING = 'Each tier starts at a higher quantity than the one before.';
const TAKEN = 'That code is taken.';
const REFUSAL: FormModalError = { message: 'Check the fields.', code: 'invalid_payload', fields: { tiers: RISING, code: TAKEN } };

/** A window refused under `tiers` and `code`, whose tiers are a group named `name` (a plain fieldset or `group`);
 *  `changed` is what it calls when the person changes a tier. */
async function refusedWindow(name: string | undefined, group: string | Component = 'fieldset') {
  let changed: () => void = () => undefined;
  const tiers = (fieldErrors: Record<string, string>) => [h('p', { 'data-testid': 'rule-tiers-error' }, fieldErrors.tiers ?? '')];
  const Window = defineComponent({
    setup() {
      changed = useGroupChange('tiers');
      return () =>
        h(
          FormModal,
          { open: true, title: 'New rule', testid: 'rule', error: REFUSAL },
          {
            default: ({ fieldErrors }: { fieldErrors: Record<string, string> }) => [
              h(group, { ref: 'tiers', name }, typeof group === 'string' ? tiers(fieldErrors) : () => tiers(fieldErrors)),
              h('p', { 'data-testid': 'rule-code-error' }, fieldErrors.code ?? ''),
            ],
          },
        );
    },
  });
  const m = await mountBase(Window);
  await nextTick();
  await flush();
  const said = (testid: string) => document.querySelector(`[data-testid="${testid}"]`)?.textContent ?? '';
  return {
    said,
    change: async () => {
      changed();
      await nextTick();
      await flush();
    },
    unmount: () => m.wrapper.unmount(),
  };
}

describe('useGroupChange', () => {
  // A FieldGroup's ref is the component, not its fieldset: the change has to come from the fieldset all the same.
  it.each([
    ['a plain fieldset', 'fieldset'],
    ['a FieldGroup', FieldGroup],
  ] as const)('a change to the group named after a refused key takes that refusal away, and only it: %s', async (_, group) => {
    const w = await refusedWindow('tiers', group);
    expect([w.said('rule-tiers-error'), w.said('rule-code-error')]).toEqual([RISING, TAKEN]);
    await w.change();
    expect([w.said('rule-tiers-error'), w.said('rule-code-error')]).toEqual(['', TAKEN]);
    w.unmount();
  });

  it('a group without the refused key’s name takes nothing away', async () => {
    const w = await refusedWindow(undefined);
    await w.change();
    expect([w.said('rule-tiers-error'), w.said('rule-code-error')]).toEqual([RISING, TAKEN]);
    w.unmount();
  });
});
