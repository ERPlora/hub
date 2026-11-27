// The four figures of some tips (TIP-F13, TIP-F14): in all, by card, in cash and any other way, in the business's money,
// with how many tips under the total; while they load, each card says so.
import { StatCard } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { mountTip } from '../__tests__/mount-tip';
import type { TipFiguresOut } from '../operations';
import TipFigures from './TipFigures.vue';

const FIGURES: TipFiguresOut = { card: 1000, cash: 250, other: 50, total: 1300, count: 3 };

async function setup(figures: TipFiguresOut | null, locale: 'en' | 'es' = 'en') {
  const m = await mountTip(TipFigures, { locale, props: { figures, testid: 'tip-day' } });
  await m.live();
  const cards = () => m.wrapper.findAllComponents(StatCard as unknown as Component).map((card) => card.props() as Record<string, unknown>);
  return { ...m, cards };
}

describe('TipFigures', () => {
  it('paints the total, by card, in cash and other ways in the business’s money, how many under the total', async () => {
    const s = await setup(FIGURES);
    expect(s.cards().map((card) => [card.label, card.value, card.testid])).toEqual([
      ['Total', '€13.00', 'tip-day-total'],
      ['By card', '€10.00', 'tip-day-card'],
      ['In cash', '€2.50', 'tip-day-cash'],
      ['Other ways', '€0.50', 'tip-day-other'],
    ]);
    expect(s.cards()[0].note).toBe('3 tips');
    expect(s.find('tip-day').classes()).toContain('ep-stat-grid');
  });

  it('says one tip in the singular, and each card loads until the figures arrive', async () => {
    expect((await setup({ ...FIGURES, count: 1 })).cards()[0].note).toBe('1 tip');
    const loading = await setup(null);
    expect(loading.cards().map((card) => card.loading)).toEqual([true, true, true, true]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(FIGURES, 'es');
    expect(s.cards().map((card) => card.label)).toEqual(['Total', 'Con tarjeta', 'En efectivo', 'Otras formas']);
    expect(s.cards()[0].note).toBe('3 propinas');
  });
});
