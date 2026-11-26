import { describe, expect, it } from 'vitest';

import { catalogOptions } from './catalogOptions';

const WORDS: Record<string, string> = {
  'whatsapp_inbox.conversation.list': 'Buscar conversaciones de WhatsApp',
  'customer.customer.list': 'Buscar clientes',
  'customer.customer.detail': 'Leer un cliente',
  'order.order.list': 'Buscar pedidos',
  'payment.payment.list': 'Buscar pagos',
};
const label = (name: string): string => WORDS[name];

describe('catalogOptions', () => {
  it('names each entry in words with its app under it, never its internal name', () => {
    const options = catalogOptions([{ name: 'whatsapp_inbox.conversation.list', app_name: 'Bandeja de WhatsApp' }], label, 'es');
    expect(options).toEqual([{ id: 'whatsapp_inbox.conversation.list', label: 'Buscar conversaciones de WhatsApp', hint: 'Bandeja de WhatsApp' }]);
  });

  it('orders by app and then by name, as the language sorts them', () => {
    const options = catalogOptions(
      [
        { name: 'payment.payment.list', app_name: 'Pagos' },
        { name: 'whatsapp_inbox.conversation.list', app_name: 'Bandeja de WhatsApp' },
        { name: 'customer.customer.detail', app_name: 'Clientes' },
        { name: 'order.order.list', app_name: 'Órdenes' },
        { name: 'customer.customer.list', app_name: 'Clientes' },
      ],
      label,
      'es',
    );
    expect(options.map((option) => [option.hint, option.label])).toEqual([
      ['Bandeja de WhatsApp', 'Buscar conversaciones de WhatsApp'],
      ['Clientes', 'Buscar clientes'],
      ['Clientes', 'Leer un cliente'],
      ['Órdenes', 'Buscar pedidos'],
      ['Pagos', 'Buscar pagos'],
    ]);
  });
});
