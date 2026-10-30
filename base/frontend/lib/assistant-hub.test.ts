// The Hub's configuration of the shared assistant (`@erplora/ui/components`, `configureAssistant`, done in main.ts):
// a turn goes to `base.assistant.turn`'s route; the allowance, a dictation and a report go through base's operations;
// whoever sees the Home uses it and whoever administers the business upgrades the plan, on erplora.com's page the
// Home's block gives; the verbs of the writes and the platform's screens are base's catalogue (the server's guardrail
// keeps them complete: base/tests/test_assistant.py); a write a manager must approve goes through APP-BASE-5's
// approvals (BASE-G118); and the empty conversation offers the setup's shortcuts (BASE-G121).
import {
  type AssistantCard,
  createAssistant,
  type PendingCall,
  type TurnBody,
  type TurnFrame,
  type TurnOptions,
} from '@erplora/ui/components';
import { ApiError } from '@erplora/ui/sdk';
import type { ShellSession } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, memoryStorage, mountBase, OWNER } from '../__tests__/mount-base';
import en from '../locale/en.json';
import es from '../locale/es.json';
import type { SetupItem, SetupStatus } from '../operations';
import { approvalPass, withApproval } from './approval';
import { actionKey, HUB_ASSISTANT, hubApproval, placeKey, platformScreenKey, setupShortcuts } from './assistant-hub';

afterEach(() => {
  document.body.innerHTML = '';
});

/** A session that may do what `permissions` says, as the shell's. */
const session = (permissions: string[]) => ({ can: (permission: string) => permissions.includes(permission) }) as ShellSession;

/** The words of base's catalogue a key names, as the screen says them. */
const said = (catalogue: unknown) => (key: string) =>
  String(key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], catalogue));

describe('HUB_ASSISTANT: where things go', () => {
  it("a turn goes to base.assistant.turn's route, and a manager's pass with it only while the turn is repeated", async () => {
    expect(HUB_ASSISTANT.turnUrl).toBe('/api/assistant/turn');
    const QUESTION = { operation: 'demo.item.create', label: 'Create an item', fingerprint: 'f'.repeat(64) };
    const passes: (string | undefined)[] = [];
    await withApproval(
      async () => {
        passes.push(HUB_ASSISTANT.elevationToken!());
        if (passes.length === 1) throw new ApiError(403, 'requires_elevation', 'x', undefined, { approval: QUESTION });
      },
      { ask: async () => 'elev_pass' },
    );
    expect(passes).toEqual([undefined, 'elev_pass']);
    expect([HUB_ASSISTANT.elevationToken!(), approvalPass()]).toEqual([undefined, undefined]);
  });

  it("the allowance, a dictation and a report go through base's operations, with the page's client", async () => {
    const sent: [string, unknown][] = [];
    const m = await mountBase(
      { template: '<div />' },
      {
        onApi: ({ url, init }) => {
          const path = url.replace(/^.*\/api/, '/api');
          sent.push([path, init.body ? JSON.parse(String(init.body)) : null]);
          if (path === '/api/assistant/usage') return Response.json({ used: 3, limit: 30, resets_at: null, demo: false });
          if (path === '/api/assistant/transcribe') return Response.json({ text: 'dos cafés', language: 'es' });
          return Response.json({ sent: true, duplicate: false });
        },
      },
    );
    expect(await HUB_ASSISTANT.usage!(m.client)).toEqual({ used: 3, limit: 30, resets_at: null, demo: false });
    expect(await HUB_ASSISTANT.transcribe!(m.client, { audio: 'dm96', mime_type: 'audio/webm', language: 'es' })).toMatchObject({
      text: 'dos cafés',
    });
    const report = { message_id: 'b1', reason: 'other' as const, answer: 'Hola' };
    await HUB_ASSISTANT.report!(m.client, report);
    expect(sent).toEqual([
      ['/api/assistant/usage', null],
      ['/api/assistant/transcribe', { audio: 'dm96', mime_type: 'audio/webm', language: 'es' }],
      ['/api/assistant/report', report],
    ]);
  });
});

describe('HUB_ASSISTANT: who', () => {
  it('whoever sees the Home uses the assistant (BASE-G110)', () => {
    expect(HUB_ASSISTANT.canUse!(session(EMPLOYEE.permissions))).toBe(true);
    expect(HUB_ASSISTANT.canUse!(session(['demo.view']))).toBe(false);
  });

  it('whoever administers the business upgrades the plan (gh:hub#1259)', () => {
    expect(HUB_ASSISTANT.canUpgrade!(session(OWNER.permissions))).toBe(true);
    expect(HUB_ASSISTANT.canUpgrade!(session(EMPLOYEE.permissions))).toBe(false);
  });

  it("the plan's page is erplora.com's the Home's block gives; without it, none", () => {
    expect(HUB_ASSISTANT.planUrl!()).toBe('');
    const block = Object.assign(document.createElement('script'), { type: 'application/json', id: 'hub-home' });
    block.textContent = JSON.stringify({ plan_url: 'https://erplora.com/hubs/a/plan' });
    document.body.append(block);
    expect(HUB_ASSISTANT.planUrl!()).toBe('https://erplora.com/hubs/a/plan');
  });
});

describe("the verb of a write (base's catalogue)", () => {
  it('is the configuration the card and the receipts use', () => {
    expect(HUB_ASSISTANT.verbKey).toBe(actionKey);
    expect(HUB_ASSISTANT.placeKey).toBe(placeKey);
    expect(HUB_ASSISTANT.screenKey).toBe(platformScreenKey);
  });

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
    const verb = (operation: string): [string, string] => [said(es)(actionKey(operation)), said(en)(actionKey(operation))];
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

describe("the platform's screens (base's catalogue)", () => {
  it('a receipt names the screen the server gives by its key; an app is no screen of the platform', () => {
    expect(placeKey('settings')).toBe('base.assistant.screens.settings');
    expect([said(es)(placeKey('settings')!), said(en)(placeKey('settings')!)]).toEqual(['Ajustes', 'Settings']);
    expect(placeKey(undefined)).toBeNull();
    expect(placeKey('toString')).toBeNull();
    expect(placeKey('invoice')).toBeNull();
  });

  it('a path of the platform is named by its screen; any other, by the menu', () => {
    expect(platformScreenKey('/')).toBe('base.assistant.screens.home');
    expect(platformScreenKey('/settings')).toBe('base.assistant.screens.settings');
    expect(platformScreenKey('/employees')).toBe('base.assistant.screens.employees');
    expect(platformScreenKey('/customer/customers')).toBeNull();
    expect(platformScreenKey('toString')).toBeNull();
  });
});

function item(fields: Partial<SetupItem>): SetupItem {
  return {
    key: 'base.x',
    app: 'base',
    state: 'pending',
    level: 'functional',
    required: true,
    actionable: true,
    title: 'Paso',
    description: '',
    icon: 'ion:cube-outline',
    route: '/',
    order: 0,
    ...fields,
  };
}

function status(items: SetupItem[]): SetupStatus {
  return { total: items.length, pending: items.filter((row) => row.state === 'pending').length, unavailable: 0, blocking_pending: 0, items };
}

describe('setupShortcuts (BASE-G121; gh:hub#373)', () => {
  it('«What is left to set up?» and, of what is pending for this person, up to four, in the checklist’s order', () => {
    const steps = ['A', 'B', 'C', 'D', 'E'].map((title) => item({ key: `base.${title}`, title }));
    expect(setupShortcuts(status(steps))).toEqual([
      { key: 'base.assistant.shortcuts.missing' },
      { key: 'base.assistant.shortcuts.step', title: 'A' },
      { key: 'base.assistant.shortcuts.step', title: 'B' },
      { key: 'base.assistant.shortcuts.step', title: 'C' },
      { key: 'base.assistant.shortcuts.step', title: 'D' },
    ]);
  });

  it('never a step already done, not available, or only an administrator can do', () => {
    const steps = [
      item({ title: 'Hecho', state: 'done' }),
      item({ title: 'Luego', state: 'unavailable' }),
      item({ title: 'Del jefe', actionable: false }),
      item({ title: 'Mío' }),
    ];
    expect(setupShortcuts(status(steps)).map((shortcut) => shortcut.title)).toEqual([undefined, 'Mío']);
  });

  it('without the checklist read, only «What is left to set up?»', () => {
    expect(setupShortcuts(undefined)).toEqual([{ key: 'base.assistant.shortcuts.missing' }]);
  });
});

describe('a write a manager must approve (BASE-G118, with APP-BASE-5’s approvals)', () => {
  const QUESTION = { operation: 'demo.item.create', label: 'Create an item', fingerprint: 'f'.repeat(64) };
  const CREATE: PendingCall = { call_id: 'c1', name: 'demo__item__create', arguments: '{"name":"Mesa 4"}' };
  const CARD: AssistantCard = {
    operation: 'demo.item.create', app: 'demo', app_name: 'Demo', action: 'create', risk: 'normal',
    fields: [{ name: 'name', label: 'Name', kind: 'text', value: 'Mesa 4' }], count: null, confirm_word: '', blocked: false,
  };
  const asked = {
    role: 'assistant' as const,
    content: '',
    tool_calls: [{ id: 'c1', type: 'function' as const, function: { name: CREATE.name, arguments: CREATE.arguments } }],
  };
  const done = (fields: Partial<Extract<TurnFrame, { type: 'done' }>> = {}): TurnFrame => ({
    type: 'done', append: [], pending: [], continuation: null, ...fields,
  });
  const needsApproval = () =>
    new ApiError(403, 'requires_elevation', 'This needs a manager’s approval.', undefined, { approval: QUESTION });

  /** A Hub that answers each POST with the frames of `script`, in order; it records each body. */
  function hub(...script: (TurnFrame[] | Error)[]) {
    const bodies: TurnBody[] = [];
    const post = vi.fn(async (body: TurnBody, options: TurnOptions) => {
      bodies.push(JSON.parse(JSON.stringify(body)) as TurnBody);
      const next = script.shift();
      if (!next) throw new Error('nothing scripted');
      if (next instanceof Error) throw next;
      for (const frame of next) options.onFrame(frame);
    });
    return { post, bodies };
  }

  async function waitingOnCard(post: ReturnType<typeof hub>['post'], ask: (q: typeof QUESTION) => Promise<string | null>) {
    const assistant = createAssistant({ post, storage: memoryStorage(), openStorage: memoryStorage(), approval: hubApproval(ask) });
    assistant.forUser('u1');
    await assistant.ask('Crea la Mesa 4');
    expect(assistant.state.confirm?.call).toEqual(CREATE);
    return assistant;
  }

  it("the Hub's approval asks in the dialog «An approval is needed» unless told otherwise", () => {
    expect(HUB_ASSISTANT.approval).toBeDefined();
  });

  it('its yes asks who approves, as the screen does, and the same turn goes again with the pass', async () => {
    const { post, bodies } = hub(
      [{ type: 'confirm', card: CARD, call: CREATE }, done({ append: [asked], pending: [CREATE] })],
      needsApproval(),
      [
        { type: 'executed', call_id: 'c1', name: 'demo.item.create', app: 'demo', kind: 'command', outcome: 'ok', code: '' },
        { type: 'text', text: 'Hecho.' },
        done({ append: [{ role: 'tool', tool_call_id: 'c1', content: '{}' }, { role: 'assistant', content: 'Hecho.' }] }),
      ],
    );
    const ask = vi.fn(async () => 'elev_pass');
    const assistant = await waitingOnCard(post, ask);
    await assistant.decide(true);
    expect(ask).toHaveBeenCalledWith(QUESTION);
    expect(bodies[2]).toEqual(bodies[1]);
    expect(bodies[1].decision).toEqual({ call_id: 'c1', accepted: true, typed: '', stop: false });
    const answer = assistant.state.thread.bubbles.at(-1)!;
    expect(answer.text).toBe('Hecho.');
    expect(answer.error).toBeUndefined();
    expect(answer.executed).toEqual([{ name: 'demo.item.create', app: 'demo', outcome: 'ok' }]);
  });

  it('when nobody approves, the write is not done and the model is told, as with «Cancel»', async () => {
    const { post, bodies } = hub(
      [{ type: 'confirm', card: CARD, call: CREATE }, done({ append: [asked], pending: [CREATE] })],
      needsApproval(),
      [
        { type: 'executed', call_id: 'c1', name: 'demo.item.create', app: 'demo', kind: 'command', outcome: 'cancelled', code: 'base.assistant_not_confirmed' },
        { type: 'text', text: 'No lo he hecho.' },
        done(),
      ],
    );
    const assistant = await waitingOnCard(post, async () => null);
    await assistant.decide(true);
    expect(bodies[2].decision).toEqual({ call_id: 'c1', accepted: false, typed: '', stop: false });
    const answer = assistant.state.thread.bubbles.at(-1)!;
    expect(answer.error).toBeUndefined();
    expect(answer.executed).toEqual([{ name: 'demo.item.create', app: 'demo', outcome: 'cancelled' }]);
  });

  it('any other refusal is no approval nobody gave', () => {
    const approval = hubApproval(async () => null);
    expect(approval.declined(needsApproval())).toBe(true);
    expect(approval.declined(new ApiError(403, 'forbidden', 'No.'))).toBe(false);
    expect(approval.declined(new TypeError('Failed to fetch'))).toBe(false);
  });
});
