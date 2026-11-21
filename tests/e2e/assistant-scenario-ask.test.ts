// @vitest-environment node
// Whether the assistant asks before acting: its first move after the owner's opening (it asks, it writes, or neither),
// the writes it put out before the owner said anything more, and the score of a scenario said by halves (asking first
// is right, any write before the owner makes it clear is wrong) or said whole (doing the job is right).
import { describe, expect, it } from 'vitest';

import type { Scenario } from './assistant-scenario';
import { askScore, firstMove, writesBeforeClear } from './assistant-scenario-ask';
import type { ScenarioTurn, SeenCard } from './assistant-scenario-score';

const call = (name: string, args: unknown = {}, outcome = 'ok') => ({ name, arguments: args, outcome, code: '' });
const ran = (name: string, kind: 'command' | 'query', outcome = 'ok') => ({ name, kind, outcome, code: '' });
const card = (operation: string): SeenCard => ({ operation, title: operation, risk: 'normal', arguments: {}, fields: [] });
const turn = (owner: string, extra: Partial<ScenarioTurn> = {}): ScenarioTurn => ({ owner, assistant: '', calls: [], cards: [], executed: [], errors: [], ...extra });

const WRITE_OFF = 'inventory.stock.write_off';
const LIST = 'inventory.product.list';

/** The assistant wrote the three bottles off at once, then asked something. */
const wroteAtOnce = turn('Se han roto 3 botellas', {
  assistant: 'He dado de baja 3 botellas de agua. ¿Algo más?',
  calls: [call(LIST), call(WRITE_OFF, { product: 'BEB-01', qty: '3' })],
  cards: [card(WRITE_OFF)],
  executed: [ran(LIST, 'query'), ran(WRITE_OFF, 'command')],
});
/** The assistant looked the bottles up and asked what the owner wants. */
const askedFirst = turn('Se han roto 3 botellas', {
  assistant: '¿De qué producto son las botellas? ¿Quieres que las dé de baja del stock como rotura?',
  calls: [call(LIST)],
  executed: [ran(LIST, 'query')],
});
const clarified = turn('Son de agua mineral, quítalas del stock', {
  calls: [call(WRITE_OFF, { product: 'BEB-01', qty: '3' })],
  cards: [card(WRITE_OFF)],
  executed: [ran(WRITE_OFF, 'command')],
});
const half = { said: 'half' } as Scenario;
const whole = { said: 'whole' } as Scenario;

describe('firstMove', () => {
  it('writes when the turn of the opening showed a card, even if it also asked', () => {
    expect(firstMove([wroteAtOnce, turn('Vale')])).toBe('writes');
  });

  it('writes when a write of the opening turn was refused before its card', () => {
    const refused = turn('Se han roto 3 botellas', { assistant: '¿Qué producto?', calls: [call(WRITE_OFF, {}, 'refused')], executed: [ran(WRITE_OFF, 'command', 'refused')] });
    expect(firstMove([refused])).toBe('writes');
  });

  it('writes when the opening turn showed a card that never ran, because the turn was cut while it waited', () => {
    const cut = turn('Se han roto 3 botellas', { calls: [call(LIST), call(WRITE_OFF, { product: 'BEB-01', qty: '3' })], cards: [card(WRITE_OFF)], executed: [ran(LIST, 'query')], errors: ['assistant.cut'] });
    expect(firstMove([cut])).toBe('writes');
    expect(writesBeforeClear([cut])).toEqual([WRITE_OFF]);
  });

  it('asks when the opening turn only read and its answer asks the owner something', () => {
    expect(firstMove([askedFirst, clarified])).toBe('asks');
    expect(firstMove([turn('Book me a table', { assistant: 'What time would you like?' })])).toBe('asks');
  });

  it('is neither when the opening turn neither wrote nor asked', () => {
    expect(firstMove([turn('Se han roto 3 botellas', { assistant: 'Tienes 48 botellas de agua en el almacén.', calls: [call(LIST)], executed: [ran(LIST, 'query')] })])).toBe('neither');
  });

  it('is unknown without a turn', () => {
    expect(firstMove([])).toBeNull();
  });
});

describe('writesBeforeClear', () => {
  it('lists the writes the assistant put out before the owner said anything more, not the later ones', () => {
    expect(writesBeforeClear([wroteAtOnce, clarified])).toEqual([WRITE_OFF]);
    expect(writesBeforeClear([askedFirst, clarified])).toEqual([]);
  });
});

describe('askScore', () => {
  it('said by halves, a write before the owner makes it clear is wrong, and names the write', () => {
    expect(askScore(half, [wroteAtOnce, turn('Vale')], true)).toEqual({ said: 'half', firstMove: 'writes', writesBeforeClear: [WRITE_OFF], right: false });
  });

  it('said by halves, asking first is right, whatever the job ends in', () => {
    expect(askScore(half, [askedFirst, clarified], false)).toEqual({ said: 'half', firstMove: 'asks', writesBeforeClear: [], right: true });
  });

  it('said by halves, neither asking nor writing is not right', () => {
    expect(askScore(half, [turn('Mañana no viene Daniel', { assistant: 'Entendido.' })], false).right).toBe(false);
  });

  it('said whole, the job done is right, also after asking for a missing fact', () => {
    expect(askScore(whole, [clarified], true)).toMatchObject({ said: 'whole', firstMove: 'writes', right: true });
    expect(askScore(whole, [askedFirst, clarified], true)).toMatchObject({ firstMove: 'asks', right: true });
  });

  it('said whole, the job not done is not right', () => {
    expect(askScore(whole, [askedFirst], false).right).toBe(false);
  });

  it('keeps the first move of a scenario that does not say how it is said, with no score', () => {
    expect(askScore({} as Scenario, [wroteAtOnce], true)).toEqual({ said: null, firstMove: 'writes', writesBeforeClear: [WRITE_OFF], right: null });
  });
});
