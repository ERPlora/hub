// BASE-G115 and G116: what the card of a write says before it runs — its action and app by their names, each datum
// in words (an amount in the business's currency, never in cents: gh:hub#1045). Cases of the old hub's
// `assistant-confirm.test.ts` and `assistant-danger.test.ts`.
import { describe, expect, it } from 'vitest';

import { actionKey, type AssistantCard, cardLine, fieldLabelKey, fieldLines, fieldText, typedMatches } from './assistant-card';

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
  it('is named by its own verb, never by the operation', () => {
    expect(actionKey('create')).toBe('base.assistant.card.actions.create');
    expect(actionKey('bulk_delete')).toBe('base.assistant.card.actions.bulk_delete');
    // FIX-HUB-BASE-ASSISTANT-CARD-RECTIFY-SAYS-DO-THIS-IN-INVOICING: these were «Do this» (a closed list of 24 verbs);
    // every action the assistant may run now has its own (guardrail: base/tests/test_assistant.py).
    expect(actionKey('rectify')).toBe('base.assistant.card.actions.rectify');
    expect(actionKey('settle')).toBe('base.assistant.card.actions.settle');
  });

  it('only one no catalogue names is «Do this»', () => {
    expect(actionKey('frobnicate')).toBe('base.assistant.card.actions.other');
    expect(actionKey('toString')).toBe('base.assistant.card.actions.other');
  });
});

describe('each datum', () => {
  it('an amount marked in cents is written in the business’s currency', () => {
    expect(fieldText(card().fields[1], opts)).toBe('15,00\u00a0€');
  });

  it('an amount marked signed says over or short as Cash register does: + over, - short, none at zero', () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-POSITIVE-DIFFERENCE-WITHOUT-SIGN: a difference over came as «137,90 €», like an
    // amount, while only the one short had its sign.
    const difference = (value: number) => ({ name: 'difference', label: 'Diferencia', kind: 'money' as const, value, signed: true });
    expect(fieldText(difference(13790), opts)).toBe('+137,90 €');
    expect(fieldText(difference(-490), opts)).toBe('-4,90 €');
    expect(fieldText(difference(0), opts)).toBe('0,00 €');
    expect(fieldText(difference(13790), { ...opts, locale: 'en' })).toBe('+€137.90');
    // Until the business's currency is known, the figure alone, with its sign.
    expect(fieldText(difference(13790), { locale: 'en', t })).toBe('+137.90');
    // Any other amount, positive as it is, never gets one; nor does a datum that is no amount, whatever it says.
    expect(fieldText(card().fields[1], opts)).toBe('15,00 €');
    expect(fieldText({ name: 'duration', label: 'Duration', kind: 'text', value: 1500, signed: true }, opts)).toBe('1500');
  });

  it('an amount that carries its own currency (a preview’s, as its read answers it) is written in it, not the business’s', () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: an invoice issued in euros, rectified once the
    // business had moved to Poland, showed «-121,00 zł» on the card.
    const PLN = { currency: 'PLN', decimals: 2 };
    const total = { name: 'total_amount', label: 'Total', kind: 'money' as const, value: -12100, money: EUR };
    expect(fieldText(total, { ...opts, money: PLN })).toBe('-121,00 €');
    expect(fieldText(total, { locale: 'en', money: PLN, t })).toBe('-€121.00');
    // Even before the business's is known; with its sign when it is a difference.
    expect(fieldText(total, { locale: 'es-ES', t })).toBe('-121,00 €');
    expect(fieldText({ ...total, value: 4200, signed: true }, { ...opts, money: PLN })).toBe('+42,00 €');
    // One that carries none, in the business's, as before.
    expect(fieldText({ ...total, money: null }, { ...opts, money: PLN })).toBe('-121,00 zł');
    expect(fieldText(card().fields[1], { ...opts, money: PLN })).toBe('15,00 zł');
  });

  it('an amount is in the minor unit of its currency: a yen invoice’s total is not a hundred times less', () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: Invoicing answers ¥12,100 as 12100.
    const JPY = { currency: 'JPY', decimals: 0 };
    const total = { name: 'total_amount', label: 'Total', kind: 'money' as const, value: -12100, money: JPY };
    expect(fieldText(total, { ...opts, locale: 'en' })).toBe('-¥12,100');
    expect(fieldText(card().fields[1], { locale: 'en', money: JPY, t })).toBe('¥1,500');
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
    // The app a card turns on or off (base.app.enable/disable, PLAN-HUB §9): «App» in both languages.
    expect(fieldLabelKey('app')).toBe('base.assistant.card.fields.app');
    expect(fieldLabelKey('tax_category_key')).toBeNull();
  });
});

describe('the lines of a dangerous write', () => {
  it('each datum by its name in the person’s language, else by the label the server gives it, and its value in words', () => {
    // BASE-F98: what the write sends and what it will do (its preview) are both said this way.
    expect(fieldLines(card().fields.slice(0, 2), opts)).toEqual([
      'base.assistant.card.fields.name: Corte caballero',
      'base.assistant.card.fields.price: 15,00\u00a0€',
    ]);
    expect(fieldLines([{ name: 'expected_balance', label: 'Efectivo esperado', kind: 'money', value: 23000 }], opts)).toEqual([
      'Efectivo esperado: 230,00\u00a0€',
    ]);
    expect(fieldLines([], opts)).toEqual([]);
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
