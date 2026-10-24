// BASE-G117: what the assistant says, checked against what really ran in the turn (gh:hub#1039). Cases of the old
// hub's `assistant-grounding.test.ts` and `assistant-claims.test.ts`.
import { describe, expect, it } from 'vitest';

import { type Executed, groundingNotices } from './assistant-grounding';

const ran = (outcome: Executed['outcome'], kind: Executed['kind'] = 'command'): Executed => ({
  name: 'demo.item.create',
  kind,
  outcome,
});
const ID = '0193e1c2-7a4b-7c3d-9e8f-0a1b2c3d4e5f';

function notices(answer: string, executed: Executed[] = [], extra: { results?: string[]; question?: string } = {}) {
  return groundingNotices({ answer, executed, results: extra.results ?? [], question: extra.question ?? '', screenExists: () => true });
}

describe('a change claimed', () => {
  it('is flagged when no write ran at all', () => {
    expect(notices('He creado el elemento Mesa 4.')).toEqual(['claimed_change']);
  });

  it('stays silent when the write really ran', () => {
    expect(notices('He creado el elemento Mesa 4.', [ran('ok')])).toEqual([]);
  });

  it('a cancelled, failed or refused write had no effect', () => {
    for (const outcome of ['cancelled', 'error', 'refused'] as const) {
      expect(notices('Listo, queda guardado.', [ran(outcome)])).toEqual(['claimed_change']);
    }
  });

  it('a read that ran is no write', () => {
    expect(notices('Se ha actualizado el precio.', [ran('ok', 'query')])).toEqual(['claimed_change']);
  });

  it('is caught in English as well', () => {
    expect(notices('The item has been created.')).toEqual(['claimed_change']);
    expect(notices("I've updated the price.")).toEqual(['claimed_change']);
  });

  it('an ordinary answer is left alone', () => {
    expect(notices('Tienes 3 elementos abiertos.')).toEqual([]);
    expect(notices('¿Quieres que lo cree?')).toEqual([]);
  });
});

describe('an identifier', () => {
  it('that the turn never read is flagged', () => {
    expect(notices(`El elemento es ${ID}.`, [ran('ok', 'query')], { results: ['{"rows": []}'] })).toEqual(['unread_id']);
  });

  it('that a tool really returned is accepted', () => {
    expect(notices(`El elemento es ${ID}.`, [ran('ok', 'query')], { results: [`{"id": "${ID}"}`] })).toEqual([]);
  });

  it('that the person wrote is accepted', () => {
    expect(notices(`Busco ${ID}.`, [], { question: `¿Qué es ${ID}?` })).toEqual([]);
  });

  it('ordinary words and numbers are no identifiers', () => {
    expect(notices('Vendiste 1234 cañas el 2026-10-24 en la mesa 4.')).toEqual([]);
  });
});

describe('a screen', () => {
  it('that this hub does not serve is flagged', () => {
    const found = groundingNotices({
      answer: 'Ve a [Informes](/reports) o a [Ajustes](/settings).',
      executed: [],
      results: [],
      question: '',
      screenExists: (path) => path === '/settings',
    });
    expect(found).toEqual(['unknown_screen']);
  });

  it('that it serves is accepted', () => {
    expect(notices('Ve a [Ajustes](/settings).')).toEqual([]);
  });
});
