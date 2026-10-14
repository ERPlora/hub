// «You have a check in progress» (SALE-F17 step 4): before resuming another check while this one has
// lines — «Park it and open», «Delete it and open» (only for whoever may void) or «Cancel».
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import DirtyCheckDialog from './DirtyCheckDialog.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const m = await mountSale(
    {
      setup: () => () =>
        h(DirtyCheckDialog, {
          open: open.value,
          'onUpdate:open': (v: boolean) => (open.value = v),
          canPark: true,
          canDiscard: true,
          pending: false,
          error: null,
          ...props,
        }),
    },
    { locale },
  );
  await settle();
  return { ...m, open, dialog: () => m.wrapper.findComponent(DirtyCheckDialog) };
}

describe('DirtyCheckDialog', () => {
  it('asks what to do with the check on screen', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-dirty-title').text()).toBe('Tienes una cuenta a medias');
    expect(m.find('pos-dirty-body').text()).toBe('¿Qué hacemos con la cuenta actual?');
    expect(m.find('pos-dirty-park').text()).toBe('Aparcarla y abrir');
    expect(m.find('pos-dirty-discard').text()).toBe('Eliminarla y abrir');
    expect(m.find('pos-dirty-cancel').text()).toBe('Cancelar');
  });

  it('hands the choice up; «Cancel» just closes', async () => {
    const m = await setup();
    await click(m.find('pos-dirty-park').element);
    await click(m.find('pos-dirty-discard').element);
    expect(m.dialog().emitted('choose')).toEqual([['park'], ['discard']]);
    await click(m.find('pos-dirty-cancel').element);
    expect(m.open.value).toBe(false);
  });

  it('no «Delete» without the permission to void, no «Park» where parking is off', async () => {
    const m = await setup({ canDiscard: false, canPark: false });
    expect(m.find('pos-dirty-discard').exists()).toBe(false);
    expect(m.find('pos-dirty-park').exists()).toBe(false);
  });

  it('a refusal is read in the dialog and the check stays', async () => {
    const m = await setup({ error: 'The check could not be deleted. It is still open, on screen.' });
    expect(m.find('pos-dirty-error').text()).toBe('The check could not be deleted. It is still open, on screen.');
  });
});
