// BASE-G115 and G116: what the card of a write says before it runs — its action and app by their names, each datum
// in words (an amount in the business's currency, never in cents: gh:hub#1045). Cases of the old hub's
// `assistant-confirm.test.ts` and `assistant-danger.test.ts`.
import { describe, expect, it } from 'vitest';

import { actionKey, type AssistantCard, cardLine, fieldLabelKey, fieldText, typedMatches } from './assistant-card';

const EUR = { currency: 'EUR', decimals: 2 };
const t = (key: string, values?: Record<string, unknown>) => (values ? `${key}${JSON.stringify(values)}` : key);
const opts = { locale: 'es-ES', money: EUR, t };

function card(fields: Partial<AssistantCard> = {}): AssistantCard {
  return {
    operation: 'service.service.create',
    app: 'service',
    app_name: 'Servicios',
    action: 'create',
    risk: 'normal',
    fields: [
      { name: 'name', label: 'Name', kind: 'text', value: 'Corte caballero' },
      { name: 'price', label: 'Price', kind: 'money', value: 1500 },
      { name: 'online', label: 'Online', kind: 'bool', value: true },
      { name: 'note', label: 'Note', kind: 'empty', value: null },
    ],
    count: null,
    confirm_word: '',
    blocked: false,
    ...fields,
  };
}

describe('the action', () => {
  it('is named by its verb, never by the operation', () => {
    expect(actionKey('create')).toBe('base.assistant.card.actions.create');
    expect(actionKey('bulk_delete')).toBe('base.assistant.card.actions.delete');
    expect(actionKey('settle')).toBe('base.assistant.card.actions.other');
  });
});

describe('each datum', () => {
  it('an amount marked in cents is written in the business’s currency', () => {
    expect(fieldText(card().fields[1], opts)).toBe('15,00\u00a0€');
  });

  it('what is not marked as money stays a number', () => {
    expect(fieldText({ name: 'duration', label: 'Duration', kind: 'text', value: 1500 }, opts)).toBe('1500');
  });

  it('a yes or no in words, an empty one as a dash', () => {
    expect(fieldText(card().fields[2], opts)).toBe('base.assistant.card.yes');
    expect(fieldText(card().fields[3], opts)).toBe('—');
  });

  it('a list says how many, a nested object never breaks the card', () => {
    expect(fieldText({ name: 'rows', label: 'Rows', kind: 'list', value: [1, 2, 3] }, opts)).toBe(
      'base.assistant.card.items{"count":3}',
    );
    expect(fieldText({ name: 'address', label: 'Address', kind: 'object', value: { city: 'Vigo' } }, opts)).toBe('city: Vigo');
  });

  it('a known datum is named in the person’s language; another by its own title', () => {
    expect(fieldLabelKey('price')).toBe('base.assistant.card.fields.price');
    expect(fieldLabelKey('tax_category_key')).toBeNull();
  });
});

describe('the one line of a normal write', () => {
  it('says its first data, never the empty ones', () => {
    expect(cardLine(card(), opts)).toBe('Corte caballero · 15,00\u00a0€ · base.assistant.card.yes');
  });
});

describe('what a dangerous write asks to type', () => {
  it('is compared as ConfirmDialog and the server do: spaces around and case ignored', () => {
    const high = card({ risk: 'high', confirm_word: 'CONFIRMAR' });
    expect(typedMatches(high, ' CONFIRMAR ')).toBe(true);
    expect(typedMatches(high, 'confirmar')).toBe(true);
    expect(typedMatches(high, 'CONFIRMA')).toBe(false);
    expect(typedMatches(card(), '')).toBe(true);
    expect(typedMatches(card({ risk: 'high', confirm_word: '3', count: 3 }), '3')).toBe(true);
  });

  it('nothing is ever confirmed on a write that is not done from the chat', () => {
    expect(typedMatches(card({ risk: 'high', blocked: true, confirm_word: 'CONFIRMAR' }), 'CONFIRMAR')).toBe(false);
  });
});
