// While the kitchen display loads: «Loading the display…», said to a screen reader as a status, over grey Ionic cards
// shaped like tickets (an icon box, two lines of head, the dishes and the foot) that a screen reader skips.
import { describe, expect, it } from 'vitest';

import { mountKitchen } from '../__tests__/mount-kitchen';
import KdsBoardSkeleton from './KdsBoardSkeleton.vue';

describe('KdsBoardSkeleton', () => {
  it('says it is loading, as a status, over cards shaped like tickets that a screen reader skips', async () => {
    const s = await mountKitchen(KdsBoardSkeleton, {});
    const root = s.find('kitchen-display-loading');
    expect(root.attributes('role')).toBe('status');
    expect(root.text()).toBe('Loading the display…');
    const cards = root.findAll('ion-card');
    expect(cards.length).toBeGreaterThanOrEqual(3);
    expect(root.find('.ep-order-board').attributes('aria-hidden')).toBe('true');
    for (const card of cards) expect(card.findAll('ion-skeleton-text').length).toBeGreaterThanOrEqual(4);
    expect((root.find('ion-skeleton-text').element as HTMLElement & { animated?: boolean }).animated).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await mountKitchen(KdsBoardSkeleton, { locale: 'es' });
    expect(s.find('kitchen-display-loading').text()).toBe('Cargando la pantalla…');
  });
});
