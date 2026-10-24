// A bubble of the panel: the person's question as written; the assistant's answer while it is written (dots), with
// its «Go to …» (BASE-G114), the notices of what it said against what ran (BASE-G117), the receipts of the actions,
// a failure with its way out (BASE-G124, G122) and «Report a problem» under a finished answer (BASE-G123).
import { describe, expect, it } from 'vitest';

import { mountBase } from '../../__tests__/mount-base';
import type { Bubble } from '../../lib/assistant-history';
import AssistantMessage from './AssistantMessage.vue';

function answer(fields: Partial<Bubble> = {}): Bubble {
  return { id: 'b2', role: 'assistant', text: '', files: [], notices: [], done: true, question: '¿Cuántos?', ...fields };
}

function mountBubble(bubble: Bubble, extra: Record<string, unknown> = {}) {
  return mountBase(AssistantMessage, {
    locale: 'es',
    props: {
      bubble,
      screenExists: (path: string) => ['/settings', '/customer/customers'].includes(path.split('#')[0]),
      nameOf: (path: string) => ({ '/settings': 'Ajustes', '/customer/customers': 'Clientes' })[path.split('#')[0]],
      appNameOf: (app: string) => (app === 'demo' ? 'Demo' : app),
      canUpgrade: false,
      planUrl: '',
      canSpeak: false,
      ...extra,
    },
  });
}

describe('AssistantMessage', () => {
  it('the person’s question comes out as written, with its files', async () => {
    const { wrapper } = await mountBubble({ id: 'b1', role: 'user', text: '**hola**', files: ['carta.pdf'], notices: [], done: true });
    expect(wrapper.find('[data-testid="assistant-bubble-user"]').text()).toContain('**hola**');
    expect(wrapper.text()).toContain('carta.pdf');
    wrapper.unmount();
  });

  it('dots while nothing has arrived yet, and no report under an answer still being written', async () => {
    const { wrapper } = await mountBubble(answer({ done: false }));
    expect(wrapper.find('[data-testid="assistant-writing"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-report"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('an answer that ended saying nothing says so', async () => {
    const { wrapper } = await mountBubble(answer({ text: '' }));
    expect(wrapper.text()).toContain('(sin respuesta)');
    wrapper.unmount();
  });

  it('«Go to …» for each screen of this hub it names, by its menu name, and never one it does not serve', async () => {
    const { wrapper } = await mountBubble(answer({ text: 'Ve a [aquí](/settings#business), a /customer/customers o a /reports.' }));
    const goes = wrapper.findAll('[data-testid="assistant-go"]');
    expect(goes.map((button) => button.text())).toEqual(['Ir a Ajustes', 'Ir a Clientes']);
    await goes[0].trigger('click');
    expect(wrapper.emitted('go')).toEqual([['/settings#business']]);
    wrapper.unmount();
  });

  it('the notices of what it said against what ran, outside the answer', async () => {
    const { wrapper } = await mountBubble(answer({ text: 'He creado Mesa 4.', notices: ['claimed_change'] }));
    expect(wrapper.find('[data-testid="assistant-notice-claimed_change"]').text()).toBe(
      'El asistente ha dicho que hizo un cambio, pero no se ejecutó ninguna acción. No se ha modificado nada.',
    );
    wrapper.unmount();
  });

  it('a receipt of each action of the turn: done, or why not', async () => {
    const executed = [
      { name: 'demo.item.create', app: 'demo', outcome: 'ok' },
      { name: 'demo.item.delete', app: 'demo', outcome: 'cancelled' },
    ];
    const { wrapper } = await mountBubble(answer({ text: 'Listo.', executed }));
    expect(wrapper.findAll('[data-testid="assistant-receipt"]').map((row) => row.text())).toEqual([
      'Hecho: Crear en Demo',
      'No se hizo, cancelado: Borrar en Demo',
    ]);
    wrapper.unmount();
  });

  it('a failure says what happened and offers its way out', async () => {
    const { wrapper } = await mountBubble(answer({ error: 'assistant.unreachable' }));
    expect(wrapper.text()).toContain('No se pudo contactar con el asistente.');
    await wrapper.find('[data-testid="assistant-retry"]').trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
    wrapper.unmount();
  });

  it('a spent allowance: the numbers, when they come back, and the plan for who may upgrade it (gh:hub#1259)', async () => {
    const spent = answer({ error: 'assistant.quota_exceeded', details: { used: 30, limit: 30, resets_at: '2026-11-01T00:00:00Z' } });
    const owner = await mountBubble(spent, { canUpgrade: true, planUrl: 'https://erplora.com/hubs/a/plan' });
    expect(owner.wrapper.text()).toContain('Has usado todos los mensajes del asistente de este mes (30 de 30).');
    expect(owner.wrapper.text()).toContain('Se renuevan el 1 de noviembre.');
    expect(owner.wrapper.find('[data-testid="assistant-upgrade"]').attributes('href')).toBe('https://erplora.com/hubs/a/plan');
    owner.wrapper.unmount();
    const cashier = await mountBubble(spent);
    expect(cashier.wrapper.find('[data-testid="assistant-upgrade"]').exists()).toBe(false);
    expect(cashier.wrapper.text()).toContain('Pídele a quien administra el negocio que mejore el plan.');
    cashier.wrapper.unmount();
  });

  it('«Report a problem» under a finished answer, never under the panel’s own failure', async () => {
    const done = await mountBubble(answer({ text: 'Tienes 3.' }));
    await done.wrapper.find('[data-testid="assistant-report"]').trigger('click');
    expect(done.wrapper.emitted('report')).toHaveLength(1);
    done.wrapper.unmount();
    const failed = await mountBubble(answer({ error: 'assistant.unavailable' }));
    expect(failed.wrapper.find('[data-testid="assistant-report"]').exists()).toBe(false);
    failed.wrapper.unmount();
  });

  it('what was not done from the chat says so', async () => {
    const { wrapper } = await mountBubble(answer({ text: 'Hazlo en Citas.', blocked: true }));
    expect(wrapper.find('[data-testid="assistant-not-from-chat"]').exists()).toBe(true);
    wrapper.unmount();
  });
});
