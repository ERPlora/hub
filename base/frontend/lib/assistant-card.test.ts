// BASE-G115 and G116: what the card of a write says before it runs — its action and app by their names, each datum
// in words (an amount in the business's currency, never in cents: gh:hub#1045). Cases of the old hub's
// `assistant-confirm.test.ts` and `assistant-danger.test.ts`.
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import { actionKey, type AssistantCard, cardLine, fieldLabelKey, fieldLines, fieldText, typedMatches } from './assistant-card';

const EUR = { currency: 'EUR', decimals: 2 };
const t = (key: string, values?: Record<string, unknown>) => (values ? `${key}${JSON.stringify(values)}` : key);
const opts = { locale: 'es-ES', money: EUR, t };
/** The card's format with a real catalogue's words, as the screen says them. */
const said = (catalogue: unknown) => ({
  ...opts,
  t: (key: string) => String(key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], catalogue)),
});

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

  it('an operation its action’s verb does not say has its own: emptying a cart is «Vaciar», removing one of its lines «Quitar»', () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-SAYS-REMOVE-FOR-EMPTYING-A-CART: the card to empty a cart (`cart_checkout.cart.clear`)
    // said «Quitar en Carrito y pago», the verb of taking one line out; a cash count (`cash_register.count.add`) said
    // «Añadir en Caja», as if it put money in. The verb goes by the whole operation first, then by its action.
    const verb = (operation: string): [string, string] => [said(es).t(actionKey(operation)), said(en).t(actionKey(operation))];
    expect(verb('cart_checkout.cart.clear')).toEqual(['Vaciar', 'Clear']);
    expect(verb('cart_checkout.item.remove')).toEqual(['Quitar', 'Remove']);
    // Kitchen's `clear` takes a product's or a category's route away: its action's verb still says it.
    expect(verb('kitchen.routing.clear')).toEqual(['Quitar', 'Clear']);
    // A count of the drawer and a cash in or out, as «Cash register» names them («Registrar arqueo», «Registrar»).
    expect(verb('cash_register.count.add')).toEqual(['Registrar arqueo', 'Register count']);
    expect(verb('cash_register.movement.add')).toEqual(['Registrar movimiento', 'Register movement']);
    // Adding a line to a cart is adding: its action's verb.
    expect(verb('cart_checkout.item.add')).toEqual(['Añadir', 'Add']);
  });

  it('an operation the catalogue does not name goes by its action, a word of JavaScript’s included', () => {
    expect(actionKey('cart_checkout.cart.create')).toBe('base.assistant.card.actions.create');
    expect(actionKey('cart_checkout.cart.toString')).toBe('base.assistant.card.actions.other');
    expect(actionKey('toString.name.length')).toBe('base.assistant.card.actions.other');
    expect(actionKey('cart_checkout.constructor.name')).toBe('base.assistant.card.actions.other');
    expect(actionKey('cart_checkout.constructor.clear')).toBe('base.assistant.card.actions.clear');
  });
});

describe('each datum', () => {
  it('an amount marked in cents is written in the business’s currency', () => {
    expect(fieldText(card().fields[1], opts)).toBe('15,00\u00a0€');
  });

  it('an amount of four figures groups its thousands, as Sales and Payments write it (base-money-thousands-grouping)', () => {
    // The Spanish CLDR only groups from five figures: the card said «1234,56 €» where Sales says «1.234,56 €».
    const price = { name: 'price', label: 'Precio', kind: 'money' as const, value: 123456 };
    expect(fieldText(price, opts)).toBe('1.234,56\u00a0€');
    expect(fieldText({ ...price, signed: true }, opts)).toBe('+1.234,56\u00a0€');
    expect(fieldText({ ...price, value: -123456 }, opts)).toBe('-1.234,56\u00a0€');
    expect(fieldText(price, { ...opts, locale: 'en' })).toBe('€1,234.56');
    expect(fieldLines([{ ...price, name: 'expected_balance', label: 'Efectivo esperado' }], opts)).toEqual([
      'Efectivo esperado: 1.234,56\u00a0€',
    ]);
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
    expect(fieldText({ name: 'address', label: 'Address', kind: 'object', value: { city: 'Vigo' } }, opts)).toBe('Vigo');
  });
});

describe('a datum that is an object', () => {
  // FIX-HUB-BASE-ASSISTANT-CARD-OBJECT-SHOWS-INNER-KEYS-IN-ENGLISH: its inner data went by their keys, in English in
  // every language («Plantilla: name: cita_recordatorio · language: es»). Like an address on a summary or a variant
  // on a ticket, it is said by its values; its own name is the datum's.
  const template = {
    name: 'template',
    label: 'Plantilla',
    kind: 'object' as const,
    value: { name: 'cita_recordatorio', language: 'es', variables: ['Ana', '10:00'] },
  };

  it('says its values, never their keys (whatsapp_inbox.message.send’s template)', () => {
    expect(fieldText(template, opts)).toBe('cita_recordatorio · es · Ana, 10:00');
    expect(fieldLines([template], opts)).toEqual(['Plantilla: cita_recordatorio · es · Ana, 10:00']);
    const line = cardLine(card({ fields: [{ name: 'to', label: 'Teléfono', kind: 'text', value: '+34600111222' }, template] }), opts);
    expect(line).toBe('+34600111222 · cita_recordatorio · es · Ana, 10:00');
    expect(line).not.toMatch(/\b(name|language|variables):/);
  });

  it('leaves out its empty data; one with none is a dash', () => {
    expect(fieldText({ ...template, value: { name: 'cita_recordatorio', language: null, variables: [], header_sample: '' } }, opts)).toBe(
      'cita_recordatorio',
    );
    expect(fieldText({ ...template, value: { language: null, variables: [] } }, opts)).toBe('—');
  });

  it('within it, an object or a list is said the same way, and a yes or no in words', () => {
    const content = { hero: { title: 'Hola', visible: true }, gallery: [{ url: 'a.jpg' }, { url: 'b.jpg' }], footer: { visible: false } };
    expect(fieldText({ name: 'content', label: 'Contenido', kind: 'object', value: content }, opts)).toBe(
      'Hola · base.assistant.card.yes · a.jpg, b.jpg · base.assistant.card.no',
    );
  });

  it('a key that is a figure is data, not a name, and stays: the face value of what was counted', () => {
    // A JavaScript object gives its whole-number keys in ascending order, as they come.
    const denominations = { bills: { '50': 2, '20': 1 }, coins: { '0.50': 4 } };
    expect(fieldText({ name: 'denominations', label: 'Billetes y monedas', kind: 'object', value: denominations }, opts)).toBe(
      '20: 1 · 50: 2 · 0.50: 4',
    );
    // A figure written with a decimal comma is one too; one counted as nothing is left out, as any empty datum.
    expect(fieldText({ name: 'denominations', label: 'Billetes y monedas', kind: 'object', value: { '0,50': 4, '20': null } }, opts)).toBe(
      '0,50: 4',
    );
  });

  it('a key with a figure only in part of it is still a name: an address’s line1 (cart_checkout’s free fields)', () => {
    const address = { line1: 'Calle Mayor 1', '2nd_line': '2º B', postal_code: '36201', city: 'Vigo' };
    expect(fieldText({ name: 'shipping_address', label: 'Dirección de envío', kind: 'object', value: address }, opts)).toBe(
      'Calle Mayor 1 · 2º B · 36201 · Vigo',
    );
  });

  it('an amount within it is written as one on top: its currency, the same symbol, never the server’s words', () => {
    // FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS: the server said an amount inside an object in its own
    // words («1,50 US$», «1,50 PLN») and the screen the one on top in its own («1,50 $», «1,50 zł»), on one card.
    const PLN = { currency: 'PLN', decimals: 2 };
    const USD = { currency: 'USD', decimals: 2 };
    const JPY = { currency: 'JPY', decimals: 0 };
    const line = (amount: unknown) => ({ name: 'line', label: 'Línea', kind: 'object' as const, value: { text: 'Café', unit_price: amount } });
    const top = (money?: typeof USD) => ({ name: 'price', label: 'Precio', kind: 'money' as const, value: 150, money });
    // In the business's currency, the card's own.
    expect(fieldText(line({ kind: 'money', value: 150 }), { ...opts, money: PLN })).toBe('Café · 1,50 zł');
    expect(fieldText(top(), { ...opts, money: PLN })).toBe('1,50 zł');
    // In the one its write names, with its decimals.
    expect(fieldText(line({ kind: 'money', value: 150, money: USD }), opts)).toBe('Café · 1,50 $');
    expect(fieldText(top(USD), opts)).toBe('1,50 $');
    // base-money-thousands-grouping: «1500 ¥» until the platform grouped every amount from four digits on.
    expect(fieldText(line({ kind: 'money', value: 1500, money: JPY }), opts)).toBe('Café · 1.500\u00a0¥');
    // Inside a list inside an object, the same.
    const order = { lines: [{ text: 'Té', unit_price: { kind: 'money', value: 1200 } }] };
    expect(fieldText({ name: 'order', label: 'Pedido', kind: 'object', value: order }, opts)).toBe('Té · 12,00 €');
    // What only looks like one is said by its values, as any other.
    expect(fieldText(line({ kind: 'money', value: 150, note: 'x' }), opts)).toBe('Café · money · 150 · x');
    expect(fieldText(line({ kind: 'money', value: '150' }), opts)).toBe('Café · money · 150');
    expect(fieldText(line({ kind: 'cash', value: 150 }), opts)).toBe('Café · cash · 150');
  });

  it('a secret stays hidden as the server sends it', () => {
    expect(fieldText({ name: 'login', label: 'Acceso', kind: 'object', value: { user: 'ana', password: '••••••••' } }, opts)).toBe(
      'ana · ••••••••',
    );
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

  // FIX-HUB-BASE-ASSISTANT-DANGER-CARD-CALLS-THE-RECORD-BY-ITS-FIELD-NAME: transferring a check said «Registro: 5
  // (Terraza)» where Tables titles it «Cuenta»: the screen's word for a datum it knows by its name (`id`) hid the title
  // its app wrote, which the server marks `titled`.

  it('a datum its app titles is called by that title, over the screen’s word for its name', () => {
    const check = { name: 'id', kind: 'text' as const, value: '5 (Terraza)', titled: true };
    expect(fieldLines([{ ...check, label: 'Cuenta' }], said(es))).toEqual(['Cuenta: 5 (Terraza)']);
    expect(fieldLines([{ ...check, label: 'Check' }], said(en))).toEqual(['Check: 5 (Terraza)']);
  });

  it('one its app does not title keeps the screen’s word for its name, in English and in Spanish', () => {
    // The server's label for an untitled `id` is the model's («ID»), or pydantic's made-up title for another.
    const device = { name: 'id', label: 'ID', kind: 'text' as const, value: 'Barra' };
    const name = { name: 'name', label: 'Name', kind: 'text' as const, value: 'Corte caballero' };
    expect(fieldLines([device, name], said(es))).toEqual(['Registro: Barra', 'Nombre: Corte caballero']);
    expect(fieldLines([device, name], said(en))).toEqual(['Record: Barra', 'Name: Corte caballero']);
    expect(fieldLines([{ ...device, titled: false }], said(es))).toEqual(['Registro: Barra']);
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
