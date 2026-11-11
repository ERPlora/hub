// hub#1208: the Hub holds a yes to the card it answers by the fingerprint the turn puts on the call that waits
// (`pending[].shown`, base/services.py `_assistant_answer`), and a card that changed comes again instead of running.
// That needs nothing new of the shared panel (@erplora/ui): it gives back the calls that wait as the turn gave them and
// shows a card that comes after a yes. This pins both, from the Hub's side: a panel that rebuilt the calls would drop
// `shown`, and every yes would draw its card again.
import { type AssistantCard, createAssistant, type PendingCall, type TurnBody, type TurnFrame, type TurnOptions } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { memoryStorage } from '../__tests__/mount-base';

const said = { call_id: 'c1', name: 'demo__item__delete', arguments: '{"called":"mesa"}' };
const CARD_OF = (name: string): AssistantCard => ({
  operation: 'demo.item.delete', app: 'demo', app_name: 'Demo', action: 'delete', risk: 'high',
  fields: [{ name: 'called', label: 'Elemento', kind: 'text', value: name }], count: null, confirm_word: 'CONFIRMAR', blocked: false,
});
/** The call as the Hub gives it back with a card: with the fingerprint of what that card showed. */
const shown = (fingerprint: string): PendingCall => ({ ...said, shown: fingerprint }) as PendingCall;
const cardFrames = (name: string, call: PendingCall): TurnFrame[] => [
  { type: 'confirm', card: CARD_OF(name), call },
  { type: 'done', append: [], pending: [call], continuation: 'tok' },
];

/** The Hub's answers, one list of frames per POST, in order; what each POST sent, as JSON travels. */
function scripted(...answers: TurnFrame[][]) {
  const bodies: TurnBody[] = [];
  const post = async (body: TurnBody, options: TurnOptions) => {
    bodies.push(JSON.parse(JSON.stringify(body)) as TurnBody);
    for (const frame of answers.shift() ?? []) options.onFrame(frame);
  };
  return { post, bodies };
}

/** The panel of the Hub's turn `post`, after «elimina mesa»: waiting on the card of its first answer. */
async function waitingOnItsCard(post: ReturnType<typeof scripted>['post']) {
  const assistant = createAssistant({ post, storage: memoryStorage(), openStorage: memoryStorage() });
  assistant.forUser('u1');
  await assistant.ask('elimina mesa');
  return assistant;
}

describe('the yes goes with what its card showed (hub#1208)', () => {
  it('gives back the call its card waits on as the turn gave it, its fingerprint included', async () => {
    const { post, bodies } = scripted(cardFrames('Mesa 4', shown('a'.repeat(64))), [
      { type: 'done', append: [], pending: [], continuation: null },
    ]);
    const assistant = await waitingOnItsCard(post);

    await assistant.decide(true, 'CONFIRMAR');

    expect(bodies[1].decision).toMatchObject({ call_id: 'c1', accepted: true, typed: 'CONFIRMAR' });
    expect(bodies[1].pending).toEqual([shown('a'.repeat(64))]);
  });

  it('shows the new card the Hub answers a yes with, and its own yes goes with its own fingerprint', async () => {
    const { post, bodies } = scripted(
      cardFrames('Mesa 4', shown('a'.repeat(64))),
      cardFrames('Mesa', shown('b'.repeat(64))),
      [{ type: 'done', append: [], pending: [], continuation: null }],
    );
    const assistant = await waitingOnItsCard(post);

    await assistant.decide(true, 'CONFIRMAR');

    expect(assistant.state.confirm?.card.fields.map((field) => field.value)).toEqual(['Mesa']);
    await assistant.decide(true, 'CONFIRMAR');
    expect(bodies[2].pending).toEqual([shown('b'.repeat(64))]);
    expect(assistant.state.confirm).toBeNull();
  });
});
