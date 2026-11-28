// The values of a closed list an action takes (WORKBOOK FLOW-F11), in words: «High», never «high».
import { describe, expect, it } from 'vitest';

import { phrasingIn } from '../__tests__/phrasing';
import type { FieldOut } from '../operations';
import { choiceLabel, choiceOptions } from './choices';

const en = phrasingIn('en');
const es = phrasingIn('es');
const field = (name: string, choices: string[]): FieldOut => ({ name, type: 'choice', required: false, description: '', choices });

describe('a value of a closed list', () => {
  it('is named by its words in the language of the screen (hub#2729)', () => {
    expect(choiceLabel({ action: 'task.task.create', field: 'priority' }, 'high', es)).toBe('Alta');
    expect(choiceLabel({ action: 'task.task.create', field: 'priority' }, 'high', en)).toBe('High');
    expect(choiceLabel({ action: 'sale.payment_method.create', field: 'type' }, 'card', es)).toBe('Tarjeta');
    expect(choiceLabel({ action: 'website.site.save', field: 'template' }, 'classic', es)).toBe('Clásica');
  });

  it('names a status with the words of the app that keeps it, for the thing it is the status of', () => {
    expect(choiceLabel({ action: 'task.task.list', field: 'status' }, 'done', es)).toBe('Hecha');
    expect(choiceLabel({ action: 'printing.job.list', field: 'status' }, 'done', es)).toBe('Impreso');
    expect(choiceLabel({ action: 'sale.sale.list', field: 'status' }, 'voided', es)).toBe('Anulada');
    expect(choiceLabel({ action: 'payment.payment.list', field: 'status' }, 'cancelled', es)).toBe('Cancelado');
  });

  it('names a fiscal code and a value that only has digits by their words', () => {
    expect(choiceLabel({ action: 'invoice.invoice.list', field: 'invoice_type' }, 'F2', es)).toBe('Tique (F2)');
    expect(choiceLabel({ action: 'sale.sale.invoice', field: 'customer_id_type' }, '02', es)).toBe('NIF-IVA de la UE');
    expect(choiceLabel({ action: 'website.site.upload', field: 'content_type' }, 'image/png', es)).toBe('Imagen PNG');
  });

  it('names a country, a weekday and the order of a list without a word of its own', () => {
    expect(choiceLabel({ action: 'customer.customer.create', field: 'country' }, 'ES', es)).toBe('España');
    expect(choiceLabel({ action: 'customer.customer.create', field: 'country_code' }, 'DE', en)).toBe('Germany');
    expect(choiceLabel({ action: 'reservation.slot.create', field: 'day_of_week' }, '0', es)).toBe('Lunes');
    expect(choiceLabel({ action: 'staff.schedule.set', field: 'weekday' }, '6', en)).toBe('Sunday');
    expect(choiceLabel({ action: 'customer.customer.list', field: 'sort' }, '-created_at', es)).toBe('Fecha de creación, descendente');
    expect(choiceLabel({ action: 'customer.customer.list', field: 'sort' }, 'name', en)).toBe('Name, ascending');
    expect(choiceLabel({ action: 'cash_register.session.list', field: 'dir' }, 'desc', es)).toBe('Descendente');
  });

  it('says a number as it is, and a value nobody wrote words for yet in plain words', () => {
    expect(choiceLabel({ action: 'printing.printer.create', field: 'paper_width' }, '80', es)).toBe('80');
    expect(choiceLabel({ action: 'demo.item.create', field: 'mood' }, 'very_happy', en)).toBe('Very happy');
  });
});

describe('the options of a closed list', () => {
  it('are its values in the order the action gives, each with its words, and never the empty one', () => {
    expect(choiceOptions('task.task.create', field('priority', ['low', 'medium', 'high', 'urgent']), es)).toEqual([
      { value: 'low', label: 'Baja' },
      { value: 'medium', label: 'Media' },
      { value: 'high', label: 'Alta' },
      { value: 'urgent', label: 'Urgente' },
    ]);
    expect(choiceOptions('whatsapp_inbox.template.create', field('header_format', ['', 'TEXT', 'IMAGE']), es).map((option) => option.value)).toEqual(['TEXT', 'IMAGE']);
  });
});
