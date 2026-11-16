// The cart_checkout app's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, no Spanish that is the
// English pasted across, every key a page, a component or a helper uses exists, and the screens'
// established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

/** Keys whose Spanish IS the English, on purpose, and why. */
const SAME_IN_BOTH: Record<string, string> = {
  'cart_checkout.carts.columns.email': 'the old Spanish screen said «Email» too',
  'cart_checkout.carts.form.email': 'the old Spanish form said «Email» too',
  'cart_checkout.orders.columns.email': 'the old Spanish screen said «Email» too',
  'cart_checkout.carts.columns.total': '«Total» is the Spanish word too',
  'cart_checkout.orders.columns.total': '«Total» is the Spanish word too',
  'cart_checkout.carts.form.sessionPlaceholder': 'an example code, the same in any language',
};

const CATALOGUES = appCatalogues('cart_checkout', en, es);
const { EN } = CATALOGUES;

describe('cart_checkout catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only', sameInBoth: SAME_IN_BOTH, coverage: { moreFilesThan: 5, moreKeysThan: 20 } });

  it('name every status the server knows', () => {
    for (const status of ['active', 'abandoned', 'converted', 'expired']) expect(EN.has(`cart_checkout.cartStatus.${status}`), status).toBe(true);
    for (const status of ['initiated', 'paid', 'failed', 'completed']) expect(EN.has(`cart_checkout.orderStatus.${status}`), status).toBe(true);
  });

  it('keep the old screens’ words', () => {
    expectWords(CATALOGUES, [
      ['cart_checkout.tabs.carts', 'Carts', 'Carritos'],
      ['cart_checkout.tabs.orders', 'Orders', 'Pedidos'],
      ['cart_checkout.title', 'Cart & Checkout', 'Carrito y pago'],
      ['cart_checkout.carts.columns.session', 'Session', 'Sesión'],
      ['cart_checkout.carts.columns.email', 'Email', 'Email'],
      ['cart_checkout.carts.columns.status', 'Status', 'Estado'],
      ['cart_checkout.carts.columns.items', 'Items', 'Ítems'],
      ['cart_checkout.carts.columns.total', 'Total', 'Total'],
      ['cart_checkout.orders.columns.order', 'Order', 'Pedido'],
      ['cart_checkout.orders.columns.payment', 'Payment', 'Pago'],
      ['cart_checkout.cartStatus.active', 'Active', 'Activo'],
      ['cart_checkout.cartStatus.abandoned', 'Abandoned', 'Abandonado'],
      ['cart_checkout.cartStatus.converted', 'Converted', 'Convertido'],
      ['cart_checkout.cartStatus.expired', 'Expired', 'Expirado'],
      ['cart_checkout.orderStatus.initiated', 'Initiated', 'Iniciado'],
      ['cart_checkout.orderStatus.paid', 'Paid', 'Pagado'],
      ['cart_checkout.orderStatus.failed', 'Failed', 'Fallido'],
      ['cart_checkout.orderStatus.completed', 'Completed', 'Completado'],
      ['cart_checkout.carts.actions.abandon', 'Abandon', 'Abandonar'],
      ['cart_checkout.carts.actions.delete', 'Delete', 'Borrar'],
      ['cart_checkout.orders.actions.markPaid', 'Mark paid', 'Marcar pagado'],
      ['cart_checkout.orders.actions.complete', 'Complete', 'Completar'],
      ['cart_checkout.orders.actions.fail', 'Fail', 'Fallar'],
      ['cart_checkout.carts.form.name', 'Name', 'Nombre'],
      ['cart_checkout.carts.form.sessionPlaceholder', 'sess_a1b2c3', 'sess_a1b2c3'],
      // vue-i18n reads a bare «@» as a linked message: the catalogue writes it as a literal, {'@'}.
      ['cart_checkout.carts.form.emailPlaceholder', "customer{'@'}example.com", "cliente{'@'}ejemplo.com"],
      ['cart_checkout.carts.form.namePlaceholder', 'John Doe', 'Ana García'],
      ['cart_checkout.carts.form.submit', 'Save', 'Guardar'],
      ['cart_checkout.carts.search', 'Search session or email…', 'Buscar sesión o email…'],
      ['cart_checkout.orders.search', 'Search order or email…', 'Buscar pedido o email…'],
      ['cart_checkout.loading', 'Loading…', 'Cargando…'],
      ['cart_checkout.carts.empty', 'No carts.', 'Sin carritos.'],
      ['cart_checkout.orders.empty', 'No orders.', 'Sin pedidos.'],
      ['cart_checkout.carts.actionError', 'Could not complete the action', 'No se pudo completar la acción'],
      ['cart_checkout.live.retry', 'Retry', 'Reintentar'],
    ]);
  });
});
