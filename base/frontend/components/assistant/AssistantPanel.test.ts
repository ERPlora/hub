// The assistant's panel (BASE-G110 open and close, G111 the conversation, G114 go to a screen, G115 the card, G120 the
// person's conversation, G121 the setup shortcuts, G122 the allowance, G123 report, G124 offline and without a plan):
// on the right, docked beside the screen from 768 px and over it on a phone; closed with ×, Escape, the veil or
// «Go to …»; the allowance read once per opening.
import { ConfirmDialog } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, flush, memoryStorage, mountBase, OWNER } from '../../__tests__/mount-base';
import { type Assistant, createAssistant, installAssistant } from '../../lib/assistant';
import type { AssistantCard } from '../../lib/assistant-card';
import type { TurnBody, TurnFrame, TurnOptions } from '../../lib/assistant-stream';
import type { AssistantUsage, SetupItem } from '../../operations';
import AssistantPanel from './AssistantPanel.vue';
import AssistantReport from './AssistantReport.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

let assistant: Assistant;
let posted: TurnBody[];
let script: TurnFrame[][];

const answer = (text: string): TurnFrame[] => [
  { type: 'text', text },
  { type: 'done', append: [{ role: 'assistant', content: text }], pending: [], continuation: null },
];

beforeEach(() => {
  posted = [];
  script = [];
  assistant = createAssistant({
    storage: memoryStorage(),
    openStorage: memoryStorage(),
    post: async (body: TurnBody, options: TurnOptions) => {
      posted.push(JSON.parse(JSON.stringify(body)) as TurnBody);
      for (const frame of script.shift() ?? answer('ok')) options.onFrame(frame);
    },
  });
  installAssistant(assistant);
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === '(min-width: 768px)', addEventListener() {}, removeEventListener() {} }));
});

afterEach(() => {
  installAssistant(undefined);
  document.body.innerHTML = '';
  document.documentElement.className = '';
  vi.unstubAllGlobals();
});

const USAGE: AssistantUsage = { used: 3, limit: 30, resets_at: '2026-11-01T00:00:00Z', demo: false };

function step(fields: Partial<SetupItem>): SetupItem {
  return {
    key: 'base.business', app: 'base', state: 'pending', level: 'legal', required: true, actionable: true,
    title: 'Los datos de tu negocio', description: '', icon: 'ion:business-outline', route: '/settings', order: 1, ...fields,
  };
}

type Sent = { url: string; body: unknown };

async function panel(options: { usage?: AssistantUsage | Response; session?: typeof OWNER; open?: boolean } = {}) {
  const sent: Sent[] = [];
  const m = await mountBase(AssistantPanel, {
    locale: 'es',
    session: options.session ?? OWNER,
    routes: ['/settings', '/customer/customers'],
    onApi: ({ url, init }) => {
      sent.push({ url: url.replace(/^.*\/api/, '/api'), body: init.body ? JSON.parse(String(init.body)) : null });
      if (url.includes('/assistant/usage')) {
        return options.usage instanceof Response ? options.usage : Response.json(options.usage ?? USAGE);
      }
      return Response.json({ sent: true, duplicate: false });
    },
  });
  if (options.open ?? true) {
    assistant.setOpen(true);
    for (let i = 0; i < 3; i += 1) await flush();
  }
  return { ...m, sent };
}

const aside = (m: Awaited<ReturnType<typeof panel>>) => m.wrapper.get('[data-testid="assistant-panel"]');

describe('AssistantPanel', () => {
  it('closed, it paints nothing and reads nothing', async () => {
    const m = await panel({ open: false });
    expect(aside(m).attributes('data-open')).toBe('false');
    expect(aside(m).attributes('aria-hidden')).toBe('true');
    expect(m.wrapper.find('[data-testid="assistant-input"]').exists()).toBe(false);
    expect(m.sent).toEqual([]);
  });

  it('open: its title, the sentence, «What is left to set up?» and the steps this person can do', async () => {
    const m = await panel();
    const call = await m.live();
    await m.result(call, 'base.setup.status', {
      total: 3, pending: 2, unavailable: 1, blocking_pending: 1,
      items: [step({}), step({ key: 'x.done', state: 'done', title: 'Hecho' }), step({ key: 'x.admin', actionable: false, title: 'Solo admin' })],
    });
    expect(aside(m).attributes('data-open')).toBe('true');
    expect(aside(m).text()).toContain('Asistente');
    expect(aside(m).text()).toContain('Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.');
    const shortcuts = m.wrapper.findAll('[data-testid="assistant-shortcut"]');
    expect(shortcuts.map((button) => button.text())).toEqual(['¿Qué falta por configurar?', '¿Cómo configuro «Los datos de tu negocio»?']);
    await shortcuts[1].trigger('click');
    for (let i = 0; i < 3; i += 1) await flush();
    expect(posted[0].setup).toBe(true);
    expect(posted[0].messages).toEqual([{ role: 'user', content: '¿Cómo configuro «Los datos de tu negocio»?' }]);
    expect(m.wrapper.findAll('[data-testid="assistant-bubble-user"]')).toHaveLength(1);
  });

  it('opened from the setup checklist, it says so', async () => {
    const m = await panel({ open: false });
    assistant.openForSetup();
    for (let i = 0; i < 3; i += 1) await flush();
    expect(aside(m).text()).toContain('Revisa la configuración de tu negocio. Elige una opción o escribe tu duda.');
  });

  it('× and Escape close it, wherever the focus is; an Escape inside a dialog over it is the dialog’s', async () => {
    const m = await panel();
    await m.wrapper.get('[data-testid="assistant-close"]').trigger('click');
    expect(assistant.state.open).toBe(false);
    assistant.setOpen(true);
    await flush();
    await aside(m).trigger('keydown', { key: 'Escape' });
    expect(assistant.state.open).toBe(false);
    assistant.setOpen(true);
    await flush();
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(assistant.state.open).toBe(false);
    assistant.setOpen(true);
    await flush();
    const dialog = document.createElement('ion-modal');
    const field = document.createElement('input');
    dialog.append(field);
    document.body.append(dialog);
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(assistant.state.open).toBe(true);
    m.wrapper.unmount();
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(assistant.state.open).toBe(true);
  });

  it('docked beside the screen from 768 px, pushing it, without a veil', async () => {
    const m = await panel();
    expect(document.documentElement.classList.contains('assistant-docked')).toBe(true);
    expect(m.wrapper.find('[data-testid="assistant-veil"]').exists()).toBe(false);
    assistant.setOpen(false);
    await flush();
    expect(document.documentElement.classList.contains('assistant-docked')).toBe(false);
    assistant.setOpen(true);
    await flush();
    m.wrapper.unmount();
    expect(document.documentElement.classList.contains('assistant-docked')).toBe(false);
  });

  it('on a phone, over the screen with a veil that closes it', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    const m = await panel();
    expect(document.documentElement.classList.contains('assistant-docked')).toBe(false);
    await m.wrapper.get('[data-testid="assistant-veil"]').trigger('click');
    expect(assistant.state.open).toBe(false);
  });

  it('reads the allowance once per opening, and from 80 % says what is left', async () => {
    const m = await panel({ usage: { ...USAGE, used: 25 } });
    expect(m.sent.filter((s) => s.url === '/api/assistant/usage')).toHaveLength(1);
    expect(m.wrapper.get('[data-testid="assistant-usage"]').text()).toBe('Te quedan 5 de 30 mensajes este mes. Se renuevan el 1 de noviembre.');
    assistant.setOpen(false);
    await flush();
    assistant.setOpen(true);
    for (let i = 0; i < 3; i += 1) await flush();
    expect(m.sent.filter((s) => s.url === '/api/assistant/usage')).toHaveLength(2);
  });

  it('under 80 %, or when the allowance cannot be read, it says nothing of it', async () => {
    const low = await panel();
    expect(low.wrapper.find('[data-testid="assistant-usage"]').exists()).toBe(false);
    low.wrapper.unmount();
    const failed = await panel({ usage: Response.json({ code: 'base.assistant_unavailable' }, { status: 503 }) });
    expect(failed.wrapper.find('[data-testid="assistant-usage"]').exists()).toBe(false);
  });

  it('a plan without the assistant: says so, the owner gets «Upgrade plan», and nothing can be sent', async () => {
    const m = await panel({ usage: { ...USAGE, used: 0, limit: 0 } });
    expect(m.wrapper.get('[data-testid="assistant-no-plan"]').text()).toContain('Tu plan no incluye el asistente.');
    expect(m.wrapper.get('[data-testid="assistant-send"]').attributes('disabled')).toBeDefined();
    m.wrapper.unmount();
    const employee = await panel({ usage: { ...USAGE, used: 0, limit: 0 }, session: EMPLOYEE });
    expect(employee.wrapper.get('[data-testid="assistant-no-plan"]').text()).toContain('Pídele a quien administra el negocio que mejore el plan.');
  });

  it('offline: a line says it, and it can still write', async () => {
    vi.stubGlobal('navigator', { ...navigator, onLine: false });
    const m = await panel();
    expect(m.wrapper.get('[data-testid="assistant-offline"]').text()).toBe('Sin conexión: puedes escribir y enviar cuando vuelva.');
    window.dispatchEvent(new Event('online'));
    vi.stubGlobal('navigator', { ...navigator, onLine: true });
    window.dispatchEvent(new Event('online'));
    await flush();
    expect(m.wrapper.find('[data-testid="assistant-offline"]').exists()).toBe(false);
  });

  it('«Go to …» opens the screen and closes the panel', async () => {
    script.push(answer('Lo tienes en /settings#business'));
    const m = await panel();
    await assistant.ask('¿Dónde cambio el nombre?');
    await flush();
    const go = m.wrapper.get('[data-testid="assistant-go"]');
    expect(go.text()).toBe('Ir a Ajustes');
    await go.trigger('click');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/settings#business');
    expect(assistant.state.open).toBe(false);
  });

  it('a write waits on its card, over everything, and the answer goes to the turn', async () => {
    const card: AssistantCard = {
      operation: 'demo.item.create', app: 'demo', app_name: 'Demo', action: 'create', risk: 'normal',
      fields: [{ name: 'name', label: 'Name', kind: 'text', value: 'Mesa 4' }], count: null, confirm_word: '', blocked: false,
    };
    const call = { call_id: 'c1', name: 'demo__item__create', arguments: '{"name":"Mesa 4"}' };
    script.push([
      { type: 'confirm', card, call },
      { type: 'done', append: [], pending: [call], continuation: 'k1' },
    ]);
    script.push(answer('Hecho.'));
    const m = await panel();
    await assistant.ask('Crea la Mesa 4');
    for (let i = 0; i < 3; i += 1) await flush();
    const dialog = m.wrapper.findComponent(ConfirmDialog);
    expect(dialog.props('open')).toBe(true);
    dialog.vm.$emit('confirm');
    for (let i = 0; i < 3; i += 1) await flush();
    expect(posted[1].decision).toEqual({ call_id: 'c1', accepted: true, typed: '', stop: false });
    expect(dialog.props('open')).toBe(false);
  });

  it('«Report a problem» opens the report of that answer', async () => {
    script.push(answer('Hoy has vendido 120 €.'));
    const m = await panel();
    await assistant.ask('¿Cuánto he vendido?');
    await flush();
    await m.wrapper.get('[data-testid="assistant-report"]').trigger('click');
    await flush();
    expect(m.wrapper.findComponent(AssistantReport).props('bubble')).toMatchObject({ text: 'Hoy has vendido 120 €.', question: '¿Cuánto he vendido?' });
  });

  it('«New conversation» empties it; the conversation is this person’s', async () => {
    const m = await panel();
    expect(m.wrapper.find('[data-testid="assistant-new"]').exists()).toBe(false);
    await assistant.ask('Hola');
    await flush();
    expect(assistant.state.thread.user).toBe('u1');
    await m.wrapper.get('[data-testid="assistant-new"]').trigger('click');
    expect(assistant.state.thread.bubbles).toEqual([]);
  });
});
