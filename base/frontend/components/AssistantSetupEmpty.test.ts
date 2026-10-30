// The Hub's empty conversation of the assistant (BASE-G111, G121), in the shared panel's `empty` slot: the sentence —
// the setup's when the panel was opened from «Finish setting up your business» — and the shortcuts: «What is left to
// set up?» and one per pending step this person can do (up to four), each asked at once with the setup; if the
// checklist cannot be read, only the first.
import { describe, expect, it, vi } from 'vitest';

import { errorFrame, mountBase, subId } from '../__tests__/mount-base';
import type { SetupItem } from '../operations';
import AssistantSetupEmpty from './AssistantSetupEmpty.vue';

function step(fields: Partial<SetupItem>): SetupItem {
  return {
    key: 'base.business', app: 'base', state: 'pending', level: 'legal', required: true, actionable: true,
    title: 'Los datos de tu negocio', description: '', icon: 'ion:business-outline', route: '/settings', order: 1, ...fields,
  };
}

const shortcuts = (m: Awaited<ReturnType<typeof mountBase>>) =>
  m.wrapper.findAll('[data-testid="assistant-shortcut"]').map((button) => button.text());

describe('AssistantSetupEmpty', () => {
  it('the sentence and the shortcuts of the steps this person can do, each one asked at once with the setup', async () => {
    const ask = vi.fn();
    const m = await mountBase(AssistantSetupEmpty, { locale: 'es', props: { setup: false, ask } });
    expect(m.wrapper.text()).toContain('Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.');
    const call = await m.live();
    await m.result(call, 'base.setup.status', {
      total: 7, pending: 6, unavailable: 1, blocking_pending: 1,
      items: [
        step({}),
        step({ key: 'a.done', state: 'done', title: 'Hecho' }),
        step({ key: 'a.off', state: 'unavailable', title: 'Todavía no' }),
        step({ key: 'a.admin', actionable: false, title: 'Solo admin' }),
        step({ key: 'a.2', title: 'Tu numeración de facturas' }),
        step({ key: 'a.3', title: 'La impresora' }),
        step({ key: 'a.4', title: 'Tu catálogo' }),
        step({ key: 'a.5', title: 'El quinto' }),
      ],
    });
    expect(shortcuts(m)).toEqual([
      '¿Qué falta por configurar?',
      '¿Cómo configuro «Los datos de tu negocio»?',
      '¿Cómo configuro «Tu numeración de facturas»?',
      '¿Cómo configuro «La impresora»?',
      '¿Cómo configuro «Tu catálogo»?',
    ]);
    await m.wrapper.findAll('[data-testid="assistant-shortcut"]')[2].trigger('click');
    expect(ask).toHaveBeenCalledWith('¿Cómo configuro «Tu numeración de facturas»?', { setup: true });
  });

  it('opened from the checklist, the setup’s sentence', async () => {
    const m = await mountBase(AssistantSetupEmpty, { locale: 'es', props: { setup: true, ask: vi.fn() } });
    expect(m.wrapper.text()).toContain('Revisa la configuración de tu negocio. Elige una opción o escribe tu duda.');
  });

  it('a checklist that cannot be read leaves «What is left to set up?»', async () => {
    const m = await mountBase(AssistantSetupEmpty, { locale: 'es', props: { setup: false, ask: vi.fn() } });
    const call = await m.live();
    call.push(errorFrame(subId(m.client, 'base.setup.status'), 'forbidden'));
    await m.wrapper.vm.$nextTick();
    expect(shortcuts(m)).toEqual(['¿Qué falta por configurar?']);
  });
});
