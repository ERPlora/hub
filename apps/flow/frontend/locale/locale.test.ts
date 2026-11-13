// The flow app's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a component or
// a helper uses exists, and the screens' established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('flow', en, es);
const { EN, ES } = CATALOGUES;

describe('flow catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('never use the characters vue-i18n reads as syntax (@ links, {{ }}) by accident', () => {
    for (const [key, message] of [...EN, ...ES]) {
      expect(message, key).not.toMatch(/@|\{\{/);
    }
  });

  it('name every run status, trigger, step, operator and test outcome the server knows', () => {
    for (const status of ['running', 'waiting', 'succeeded', 'stopped', 'failed', 'cancelled']) expect(EN.has(`flow.history.statuses.${status}`), status).toBe(true);
    for (const kind of ['event', 'schedule', 'at', 'manual']) expect(EN.has(`flow.trigger.kinds.${kind}`), kind).toBe(true);
    for (const kind of ['command', 'query', 'condition', 'delay']) expect(EN.has(`flow.steps.add.${kind}`), kind).toBe(true);
    for (const op of ['eq', 'neq', 'in', 'exists', 'contains', 'gt', 'gte', 'lt', 'lte']) expect(EN.has(`flow.steps.operators.${op}`), op).toBe(true);
    for (const outcome of ['high_risk', 'would_run', 'stops_here', 'cannot_tell', 'waits', 'refused', 'not_allowed', 'unavailable', 'not_reached']) {
      expect(EN.has(`flow.test.outcomes.${outcome}`), outcome).toBe(true);
    }
    for (const outcome of ['done', 'found', 'not_found', 'passed', 'stopped', 'waiting', 'waited', 'failed']) expect(EN.has(`flow.history.log.${outcome}`), outcome).toBe(true);
  });

  it('call Cart & Checkout’s carts and orders by its own words: it has no online shop', () => {
    // apps/cart_checkout/WORKBOOK.md: an internal book of carts and orders, used only by staff with a
    // session in the Hub, with no shop nor public page; its flow titles are the words.
    const entries = [...EN, ...ES].filter(([key]) => /^flow\.(events|actions)\.cart_checkout__/.test(key));
    expect(entries.length).toBeGreaterThan(0);
    for (const [key, message] of entries) expect(message, key).not.toMatch(/online|en línea|\bweb\b|shop|store|tienda/i);
    expect(EN.get('flow.actions.cart_checkout__checkout__initiate')).toBe('Start the order from a cart');
    expect(ES.get('flow.actions.cart_checkout__checkout__initiate')).toBe('Iniciar el pedido desde un carrito');
  });

  it('call Payments’ methods and its cancelled payment by its own words, not Sales’ «forma de pago»', () => {
    // apps/payment/frontend/locale: the «Métodos» tab, the «Método» field, «Nuevo método», the «Cancelado»
    // status and «Cancelar pago». «Forma de pago» is how Sales names its own (`sale__payment_method__*`),
    // so the same word on both would hide which app a trigger or a step belongs to.
    const spanish = [...ES].filter(([key]) => /^flow\.(events|actions)\.payment__/.test(key));
    const methods = spanish.filter(([key]) => /\.payment__method__/.test(key));
    expect(methods.length).toBe(10);
    for (const [key, message] of spanish) expect(message, key).not.toMatch(/formas? de pago|anula/i);
    for (const [key, message] of methods) expect(message, key).toMatch(/\b(un método|métodos) de pago$/);
    expect(ES.get('flow.events.payment__payment__cancelled')).toBe('se cancela un pago');
    expect(ES.get('flow.events.payment__method__created')).toBe('se crea un método de pago');
    expect(ES.get('flow.actions.payment__method__list')).toBe('Buscar métodos de pago');
    expect(ES.get('flow.events.sale__payment_method__created')).toBe('se añade una forma de pago a las ventas');
    const english = [...EN].filter(([key]) => /^flow\.(events|actions)\.payment__method__/.test(key));
    expect(english.length).toBe(10);
    for (const [key, message] of english) expect(message, key).toMatch(/\bpayment methods?\b/);
    expect(EN.get('flow.events.payment__payment__cancelled')).toBe('a payment is cancelled');
  });

  it('keep the old screens’ words: list, editor, tabs, steps, permissions, gallery', () => {
    expectWords(CATALOGUES, [
      ['flow.title', 'Automations', 'Automatizaciones'],
      ['flow.list.new', 'New automation', 'Nueva automatización'],
      ['flow.list.heading', 'Your automations', 'Tus automatizaciones'],
      ['flow.list.search', 'Search by name, by what starts it or by what it does', 'Busca por nombre, por lo que la arranca o por lo que hace'],
      ['flow.list.count', 'Showing {shown} of {total}', 'Se ven {shown} de {total}'],
      ['flow.list.noMatch', 'Nothing here matches that.', 'Aquí no hay nada que encaje con eso.'],
      ['flow.list.clear', 'Show them all again', 'Volver a verlas todas'],
      ['flow.list.bulkEnable', 'Turn it on | Turn them on', 'Encenderla | Encenderlas'],
      ['flow.list.bulkPause', 'Pause it | Pause them', 'Ponerla en pausa | Ponerlas en pausa'],
      ['flow.list.duplicate', 'Make a copy', 'Hacer una copia'],
      ['flow.list.deleteYes', 'Yes, delete it', 'Sí, bórrala'],
      ['flow.list.deleteNo', 'Leave it', 'Déjala'],
      ['flow.active', 'Active', 'Activa'],
      ['flow.paused', 'Paused', 'En pausa'],
      ['flow.unnamed', 'Untitled automation', 'Automatización sin nombre'],
      ['flow.steps.add.command', 'Do something', 'Hacer algo'],
      ['flow.steps.add.query', 'Look something up', 'Consultar algo'],
      ['flow.steps.add.condition', 'Only continue if…', 'Solo sigue si…'],
      ['flow.steps.add.delay', 'Wait', 'Esperar'],
      ['flow.steps.none', 'No steps yet. Add the first thing this automation should do.', 'Todavía no hay pasos. Añade lo primero que debe hacer esta automatización.'],
      ['flow.trigger.when', 'When this happens…', 'Cuando pase esto…'],
      ['flow.editor.tabs.steps', 'Steps', 'Pasos'],
      ['flow.editor.tabs.test', 'Try it', 'Probar'],
      ['flow.editor.tabs.permissions', 'Permissions', 'Permisos'],
      ['flow.editor.tabs.history', 'History', 'Historial'],
      ['flow.editor.save', 'Save', 'Guardar'],
      ['flow.editor.saving', 'Saving…', 'Guardando…'],
      ['flow.permissions.grantAll', 'Allow everything it needs', 'Autorizar todo lo que necesita'],
      ['flow.permissions.missing', 'Waiting for your permission', 'Falta tu permiso'],
      ['flow.permissions.granted', 'Allowed', 'Autorizado'],
      ['flow.history.empty', 'It has not run yet.', 'Todavía no se ha ejecutado.'],
      ['flow.gallery.use', 'Use this one', 'Usar esta'],
      ['flow.gallery.guide', 'How does this work?', '¿Cómo funciona esto?'],
      ['flow.drafts.heading', 'Proposed by the assistant', 'Propuestas por el asistente'],
      ['flow.drafts.badge', 'Draft', 'Borrador'],
    ]);
  });
});
