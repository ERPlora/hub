// The panel's state (BASE-G110, G111, G115, G116, G117, G119, G120, G124): a question runs its turn — the reads the
// model asks for go on by themselves, each write waits for its card —, «Stop» keeps what was written, the conversation
// is the person's (another one on the till starts empty), and what the answer says is checked against what ran.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { memoryStorage } from '../__tests__/mount-base';
import { createAssistant, OPEN_KEY } from './assistant';
import type { AssistantCard } from './assistant-card';
import { HISTORY_KEY } from './assistant-history';
import type { PendingCall, TurnBody, TurnFrame, TurnOptions } from './assistant-stream';

const CREATE: PendingCall = { call_id: 'c1', name: 'demo__item__create', arguments: '{"name":"Mesa 4"}' };
const LIST: PendingCall = { call_id: 'r1', name: 'demo__item__list', arguments: '{}' };
const CARD: AssistantCard = {
  operation: 'demo.item.create', app: 'demo', app_name: 'Demo', action: 'create', risk: 'normal',
  fields: [{ name: 'name', label: 'Name', kind: 'text', value: 'Mesa 4' }], count: null, confirm_word: '', blocked: false,
};

function asked(...calls: PendingCall[]) {
  return {
    role: 'assistant' as const,
    content: '',
    tool_calls: calls.map((c) => ({ id: c.call_id, type: 'function' as const, function: { name: c.name, arguments: c.arguments } })),
  };
}
const done = (fields: Partial<Extract<TurnFrame, { type: 'done' }>> = {}): TurnFrame => ({
  type: 'done', append: [], pending: [], continuation: null, ...fields,
});

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

function assistantWith(post: ReturnType<typeof hub>['post'], storage = memoryStorage(), openStorage = memoryStorage()) {
  const assistant = createAssistant({ post, storage, openStorage, id: (() => { let n = 0; return () => `b${++n}`; })() });
  assistant.forUser('u1');
  assistant.setScreenCheck((path) => path === '/settings');
  return assistant;
}

describe('opening and closing (BASE-G110)', () => {
  it('the device remembers open or closed, and nothing else', () => {
    const openStorage = memoryStorage();
    const assistant = assistantWith(hub().post, memoryStorage(), openStorage);
    assistant.toggle();
    expect(assistant.state.open).toBe(true);
    expect(openStorage.getItem(OPEN_KEY)).toBe('1');
    assistant.toggle();
    expect(openStorage.getItem(OPEN_KEY)).toBe('0');
    openStorage.setItem(OPEN_KEY, '1');
    expect(assistantWith(hub().post, memoryStorage(), openStorage).state.open).toBe(true);
  });
});

describe('asking (BASE-G111)', () => {
  it('the question goes out with the whole conversation and the answer arrives into one bubble', async () => {
    const { post, bodies } = hub([
      { type: 'text', text: 'Tienes ' },
      { type: 'text', text: '3.' },
      done({ append: [{ role: 'assistant', content: 'Tienes 3.' }] }),
    ]);
    const assistant = assistantWith(post);
    await assistant.ask('¿Cuántos tengo?');
    expect(bodies[0].messages).toEqual([{ role: 'user', content: '¿Cuántos tengo?' }]);
    expect(assistant.state.thread.bubbles.map((b) => [b.role, b.text, b.done])).toEqual([
      ['user', '¿Cuántos tengo?', true],
      ['assistant', 'Tienes 3.', true],
    ]);
    expect(assistant.state.thread.conversation.at(-1)).toEqual({ role: 'assistant', content: 'Tienes 3.' });
    expect(assistant.state.busy).toBe(false);
  });

  it('an empty question with nothing attached sends nothing', async () => {
    const { post } = hub();
    await assistantWith(post).ask('   ');
    expect(post).not.toHaveBeenCalled();
  });
});

describe('several things in a row (BASE-G115, G119)', () => {
  it('the reads the model asks for go on by themselves; a write stops on its card', async () => {
    const { post, bodies } = hub(
      [done({ append: [asked(LIST)], pending: [LIST], continuation: 'tok' })],
      [
        { type: 'executed', call_id: 'r1', name: 'demo.item.list', app: 'demo', kind: 'query', outcome: 'ok', code: '' },
        { type: 'text', text: 'Lo creo.' },
        done({ append: [{ role: 'tool', tool_call_id: 'r1', content: '{"rows":[]}' }, asked(CREATE)], pending: [CREATE], continuation: 'tok2' }),
      ],
      [{ type: 'confirm', card: CARD, call: CREATE }, done({ pending: [CREATE], continuation: 'tok2' })],
    );
    const assistant = assistantWith(post);
    await assistant.ask('crea Mesa 4');
    expect(bodies.map((body) => body.pending)).toEqual([undefined, [LIST], [CREATE]]);
    expect(bodies[1].continuation).toBe('tok');
    expect(assistant.state.confirm).toEqual({ card: CARD, call: CREATE, more: false });
    expect(assistant.state.busy).toBe(true);
  });

  it('«Cancel all» is offered only when more actions wait behind this one', async () => {
    const SECOND: PendingCall = { ...CREATE, call_id: 'c2' };
    const { post } = hub([{ type: 'confirm', card: CARD, call: CREATE }, done({ append: [asked(CREATE, SECOND)], pending: [CREATE, SECOND] })]);
    const assistant = assistantWith(post);
    await assistant.ask('crea dos');
    expect(assistant.state.confirm?.more).toBe(true);
  });

  it('a write that names no record is not done from the chat: no card, the turn goes on and says so', async () => {
    const BLOCKED = { ...CARD, risk: 'high' as const, blocked: true, confirm_word: 'CONFIRMAR' };
    const { post, bodies } = hub(
      [{ type: 'confirm', card: BLOCKED, call: CREATE }, done({ append: [asked(CREATE)], pending: [CREATE] })],
      [{ type: 'text', text: 'Hazlo desde Citas.' }, done({ append: [{ role: 'tool', tool_call_id: 'c1', content: '{}' }] })],
    );
    const assistant = assistantWith(post);
    await assistant.ask('borra todas');
    expect(bodies[1].decision).toEqual({ call_id: 'c1', accepted: false, typed: '', stop: false });
    expect(assistant.state.confirm).toBeNull();
    expect(assistant.state.thread.bubbles.at(-1)).toMatchObject({ blocked: true, done: true });
  });

  it('the yes goes with its call; the no too, and the model is told', async () => {
    const { post, bodies } = hub(
      [{ type: 'confirm', card: CARD, call: CREATE }, done({ append: [asked(CREATE)], pending: [CREATE], continuation: 'tok' })],
      [
        { type: 'executed', call_id: 'c1', name: 'demo.item.create', app: 'demo', kind: 'command', outcome: 'ok', code: '' },
        { type: 'text', text: 'He creado Mesa 4.' },
        done({ append: [{ role: 'tool', tool_call_id: 'c1', content: '{"id":"x"}' }, { role: 'assistant', content: 'He creado Mesa 4.' }] }),
      ],
    );
    const assistant = assistantWith(post);
    await assistant.ask('crea Mesa 4');
    await assistant.decide(true);
    expect(bodies[1]).toMatchObject({ pending: [CREATE], continuation: 'tok', decision: { call_id: 'c1', accepted: true, typed: '', stop: false } });
    const answer = assistant.state.thread.bubbles.at(-1)!;
    expect(answer.text).toBe('He creado Mesa 4.');
    expect(answer.notices).toEqual([]);
    expect(answer.executed).toEqual([{ name: 'demo.item.create', app: 'demo', outcome: 'ok' }]);
    expect(assistant.state.confirm).toBeNull();
    expect(assistant.state.busy).toBe(false);
  });

  it('«Cancel all» stops this write and the rest of the turn', async () => {
    const { post, bodies } = hub(
      [{ type: 'confirm', card: CARD, call: CREATE }, done({ append: [asked(CREATE)], pending: [CREATE] })],
      [done({ append: [{ role: 'tool', tool_call_id: 'c1', content: '{}' }, { role: 'assistant', content: 'Vale, no hago nada.' }] })],
    );
    const assistant = assistantWith(post);
    await assistant.ask('crea Mesa 4');
    await assistant.decide(false, '', true);
    expect(bodies[1].decision).toEqual({ call_id: 'c1', accepted: false, typed: '', stop: true });
  });
});

describe('what it says against what ran (BASE-G117)', () => {
  it('a change claimed with no write that ran is flagged outside the answer', async () => {
    const { post } = hub([{ type: 'text', text: 'He creado Mesa 4.' }, done({ append: [{ role: 'assistant', content: 'He creado Mesa 4.' }] })]);
    const assistant = assistantWith(post);
    await assistant.ask('crea Mesa 4');
    expect(assistant.state.thread.bubbles.at(-1)!.notices).toEqual(['claimed_change']);
  });

  it('a screen this hub does not serve is flagged', async () => {
    const { post } = hub([{ type: 'text', text: 'Ve a [Informes](/reports).' }, done()]);
    const assistant = assistantWith(post);
    await assistant.ask('¿dónde veo informes?');
    expect(assistant.state.thread.bubbles.at(-1)!.notices).toEqual(['unknown_screen']);
  });
});

describe('failures (BASE-G124, G122)', () => {
  it('a network that is not there says so, and the question stays to try again', async () => {
    const { post, bodies } = hub(new TypeError('Failed to fetch'), [{ type: 'text', text: 'Ya.' }, done({ append: [{ role: 'assistant', content: 'Ya.' }] })]);
    const assistant = assistantWith(post);
    await assistant.ask('hola');
    expect(assistant.state.thread.bubbles.at(-1)).toMatchObject({ error: 'assistant.unreachable', done: true });
    expect(assistant.state.busy).toBe(false);
    await assistant.retry();
    expect(bodies[1].messages).toEqual([{ role: 'user', content: 'hola' }]);
    expect(assistant.state.thread.bubbles.map((b) => b.text)).toEqual(['hola', 'Ya.']);
  });

  it('a spent allowance keeps its numbers for its sentence', async () => {
    const { post } = hub([{ type: 'error', code: 'assistant.quota_exceeded', used: 30, limit: 30, resets_at: '2026-11-01T00:00:00Z', demo: false }]);
    const assistant = assistantWith(post);
    await assistant.ask('hola');
    expect(assistant.state.thread.bubbles.at(-1)).toMatchObject({ error: 'assistant.quota_exceeded', details: { used: 30, limit: 30 } });
  });

  it('a session gone is its own failure', async () => {
    const { post } = hub(new ApiError(401, 'unauthorized', 'x'));
    const assistant = assistantWith(post);
    await assistant.ask('hola');
    expect(assistant.state.thread.bubbles.at(-1)!.error).toBe('unauthorized');
  });

  it('«Stop» keeps what was written and frees the box', async () => {
    let release: () => void = () => undefined;
    const post = vi.fn(
      (_body: TurnBody, options: TurnOptions) =>
        new Promise<void>((_resolve, reject) => {
          options.onFrame({ type: 'text', text: 'Tienes' });
          options.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
          release = () => undefined;
        }),
    );
    const assistant = assistantWith(post);
    const running = assistant.ask('¿cuántos?');
    assistant.stop();
    await running;
    release();
    expect(assistant.state.thread.bubbles.at(-1)).toMatchObject({ text: 'Tienes', stopped: true, done: true });
    expect(assistant.state.busy).toBe(false);
  });
});

describe('the conversation (BASE-G120)', () => {
  it('is kept in this tab and comes back for the same person', async () => {
    const storage = memoryStorage();
    const { post } = hub([{ type: 'text', text: 'Hola' }, done({ append: [{ role: 'assistant', content: 'Hola' }] })]);
    await assistantWith(post, storage).ask('hola');
    const again = assistantWith(hub().post, storage);
    expect(again.state.thread.bubbles.map((b) => b.text)).toEqual(['hola', 'Hola']);
  });

  it('another person on the till starts empty, with nothing of the one who left (gh:hub#2538)', async () => {
    const storage = memoryStorage();
    const { post } = hub([{ type: 'text', text: 'Hola' }, done()]);
    const assistant = assistantWith(post, storage);
    await assistant.ask('hola');
    assistant.state.draft = 'a medias';
    assistant.setOpen(true);
    assistant.forUser('u2');
    expect(assistant.state.thread.bubbles).toEqual([]);
    expect(assistant.state.draft).toBe('');
    expect(assistant.state.files).toEqual([]);
    expect(assistant.state.open).toBe(false);
    expect(storage.getItem(HISTORY_KEY)).toBeNull();
  });

  it('«New conversation» empties it without leaving', async () => {
    const storage = memoryStorage();
    const { post } = hub([{ type: 'text', text: 'Hola' }, done()]);
    const assistant = assistantWith(post, storage);
    await assistant.ask('hola');
    assistant.newConversation();
    expect(assistant.state.thread.conversation).toEqual([]);
    expect(assistant.state.thread.bubbles).toEqual([]);
  });
});

describe('the setup (BASE-G121)', () => {
  it('opened from the checklist, the turns carry the setup', async () => {
    const { post, bodies } = hub([done()]);
    const assistant = assistantWith(post);
    assistant.openForSetup();
    expect(assistant.state.open).toBe(true);
    await assistant.ask('¿Qué falta por configurar?');
    expect(bodies[0].setup).toBe(true);
  });
});
