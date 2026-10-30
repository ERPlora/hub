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

function mountBubble(bubble: Bubble, extra: Record<string, unknown> = {}, locale: 'en' | 'es' = 'es') {
  return mountBase(AssistantMessage, {
    locale,
    props: {
      bubble,
      screenExists: (path: string) => ['/settings', '/customer/customers'].includes(path.split('#')[0]),
      nameOf: (path: string) => ({ '/settings': 'Ajustes', '/customer/customers': 'Clientes' })[path.split('#')[0]],
      // The menu's name of an app, in the screen's language; none for an app it does not list.
      appNameOf: (app: string) => ({ demo: 'Demo', invoice: 'Facturación' })[app],
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

  it('a receipt names the action by its own verb, in Spanish and in English, never «Do this»', async () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-RECTIFY-SAYS-DO-THIS-IN-INVOICING: «Hecho: Hacer esto en Facturación».
    const executed = [
      { name: 'invoice.invoice.rectify', app: 'invoice', app_name: 'Facturación', outcome: 'ok' },
      { name: 'invoice.invoice.mark_paid', app: 'invoice', app_name: 'Facturación', outcome: 'cancelled' },
    ];
    const es = await mountBubble(answer({ text: 'Hecho.', executed }));
    expect(es.wrapper.findAll('[data-testid="assistant-receipt"]').map((row) => row.text())).toEqual([
      'Hecho: Rectificar en Facturación',
      'No se hizo, cancelado: Registrar el cobro en Facturación',
    ]);
    es.wrapper.unmount();
    const english = executed.map((row) => ({ ...row, app_name: 'Invoicing' }));
    // The menu in the screen's language, as the shell's is.
    const en = await mountBubble(answer({ text: 'Done.', executed: english }), { appNameOf: (app: string) => ({ invoice: 'Invoicing' })[app] }, 'en');
    expect(en.wrapper.findAll('[data-testid="assistant-receipt"]').map((row) => row.text())).toEqual([
      'Done: Rectify in Invoicing',
      'Not done, cancelled: Record the payment in Invoicing',
    ]);
    en.wrapper.unmount();
  });

  it('a receipt says the verb its card said: emptying a cart «Vaciar», taking a line out «Quitar», a cash count the count', async () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-SAYS-REMOVE-FOR-EMPTYING-A-CART: «Hecho: Quitar en Carrito y pago» for an emptied cart.
    const executed = [
      { name: 'cart_checkout.cart.clear', app: 'cart_checkout', app_name: 'Carrito y pago', outcome: 'ok' },
      { name: 'cart_checkout.item.remove', app: 'cart_checkout', app_name: 'Carrito y pago', outcome: 'cancelled' },
      { name: 'cash_register.count.add', app: 'cash_register', app_name: 'Caja', outcome: 'ok' },
    ];
    const es = await mountBubble(answer({ text: 'Hecho.', executed }));
    expect(es.wrapper.findAll('[data-testid="assistant-receipt"]').map((row) => row.text())).toEqual([
      'Hecho: Vaciar en Carrito y pago',
      'No se hizo, cancelado: Quitar en Carrito y pago',
      'Hecho: Registrar arqueo en Caja',
    ]);
    es.wrapper.unmount();
    const names = { cart_checkout: 'Cart & Checkout', cash_register: 'Cash register' };
    const en = await mountBubble(answer({ text: 'Done.', executed }), { appNameOf: (app: string) => names[app as keyof typeof names] }, 'en');
    expect(en.wrapper.findAll('[data-testid="assistant-receipt"]').map((row) => row.text())).toEqual([
      'Done: Clear in Cart & Checkout',
      'Not done, cancelled: Remove in Cart & Checkout',
      'Done: Register count in Cash register',
    ]);
    en.wrapper.unmount();
  });

  it('a receipt names where it happened as the server says it: the platform by its screen, never «base»', async () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH: the menu has no section «base», so the receipt said «en base».
    const executed = [{ name: 'base.access.settings_update', app: 'base', app_name: 'Ajustes', outcome: 'cancelled' }];
    const { wrapper } = await mountBubble(answer({ text: 'No lo he hecho.', executed }));
    expect(wrapper.find('[data-testid="assistant-receipt"]').text()).toBe('No se hizo, cancelado: Cambiar en Ajustes');
    wrapper.unmount();
  });

  it('a receipt kept from a turn in another language is said whole in the screen’s: the app by its menu, the platform by its screen', async () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY (seen on its e2e): asked in English, read once
    // the person had switched to Spanish, it said «No se hizo, cancelado: Rectificar en Invoicing».
    const executed = [
      { name: 'invoice.invoice.rectify', app: 'invoice', app_name: 'Invoicing', outcome: 'cancelled' },
      { name: 'base.access.settings_update', app: 'base', app_name: 'Settings', screen: 'settings', outcome: 'ok' },
      // An app the menu does not list (gone, or not this person's): as the server named it then.
      { name: 'demo.item.create', app: 'stock', app_name: 'Almacén', outcome: 'ok' },
    ];
    const { wrapper } = await mountBubble(answer({ text: 'No lo he hecho.', executed }));
    expect(wrapper.findAll('[data-testid="assistant-receipt"]').map((row) => row.text())).toEqual([
      'No se hizo, cancelado: Rectificar en Facturación',
      'Hecho: Cambiar en Ajustes',
      'Hecho: Crear en Almacén',
    ]);
    wrapper.unmount();
  });

  it('a failure before any word: no empty bubble, the failure in its place (BASE-G124)', async () => {
    const { wrapper } = await mountBubble(answer({ error: 'assistant.unavailable' }));
    expect(wrapper.find('[data-testid="assistant-answer"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="assistant-bubble-assistant"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="assistant-failure"]').exists()).toBe(true);
    wrapper.unmount();
    const partial = await mountBubble(answer({ text: 'Hoy has', error: 'assistant.cut' }));
    expect(partial.wrapper.get('[data-testid="assistant-bubble-assistant"]').text()).toContain('Hoy has');
    partial.wrapper.unmount();
  });

  it('a failure says what happened and offers its way out', async () => {
    const { wrapper } = await mountBubble(answer({ error: 'assistant.unreachable' }));
    expect(wrapper.text()).toContain('No se pudo contactar con el asistente.');
    await wrapper.find('[data-testid="assistant-retry"]').trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
    wrapper.unmount();
  });

  it('a spent allowance and when it comes back read as two sentences, in both languages', async () => {
    const spent = answer({ error: 'assistant.quota_exceeded', details: { used: 30, limit: 30, resets_at: '2026-11-01T00:00:00Z' } });
    const es = await mountBubble(spent);
    expect(es.wrapper.get('[data-testid="assistant-failure"] p').text()).toBe(
      'Has usado todos los mensajes del asistente de este mes (30 de 30). Se renuevan el 1 de noviembre.',
    );
    es.wrapper.unmount();
    const en = await mountBubble(spent, {}, 'en');
    expect(en.wrapper.get('[data-testid="assistant-failure"] p').text()).toBe(
      "You have used all the assistant's messages of this month (30 of 30). They renew on November 1.",
    );
    en.wrapper.unmount();
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
