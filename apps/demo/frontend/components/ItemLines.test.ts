// The lines of an item, in their order; a provisional line (an optimistic overlay that the server
// has not confirmed yet) is shown faded and marked as being saved.
import { describe, expect, it } from 'vitest';

import { mountDemo } from '../__tests__/mount-demo';
import ItemLines from './ItemLines.vue';

const LINES = [
  { id: 'l1', text: 'Water', qty: '2.000', position: 1, client_line_id: 'c1' },
  { id: 'c2', text: 'Bread', qty: '0.500', position: 2, client_line_id: 'c2', pending: true },
];

describe('ItemLines', () => {
  it('shows each line with its text and its quantity, in order', async () => {
    const { wrapper } = await mountDemo(ItemLines, { props: { lines: LINES } });
    const rows = wrapper.findAll('[data-testid="demo-line"]');
    expect(rows.map((r) => r.get('[data-testid="demo-line-text"]').text())).toEqual(['Water', 'Bread']);
    expect(rows.map((r) => r.get('[data-testid="demo-line-qty"]').text())).toEqual(['× 2', '× 0.5']);
  });

  it('writes the quantity the way the language does (a Spanish 2.000 would read two thousand)', async () => {
    const { wrapper } = await mountDemo(ItemLines, { props: { lines: LINES }, locale: 'es' });
    const qty = wrapper.findAll('[data-testid="demo-line-qty"]').map((q) => q.text());
    expect(qty).toEqual(['× 2', '× 0,5']);
  });

  it('fades a provisional line and says it is being saved', async () => {
    const { wrapper } = await mountDemo(ItemLines, { props: { lines: LINES } });
    const [saved, provisional] = wrapper.findAll('[data-testid="demo-line"]');
    expect(saved.classes()).not.toContain('demo-line--pending');
    expect(saved.attributes('aria-busy')).toBe('false');
    expect(provisional.classes()).toContain('demo-line--pending');
    expect(provisional.attributes('aria-busy')).toBe('true');
    // On its own element: happy-dom's textContent of an `ion-item` host skips its label.
    expect(provisional.get('[data-testid="demo-line-pending"]').text()).toBe('Saving…');
    expect(saved.find('[data-testid="demo-line-pending"]').exists()).toBe(false);
  });

  it('says so when there are no lines', async () => {
    const { wrapper } = await mountDemo(ItemLines, { props: { lines: [] } });
    expect(wrapper.find('[data-testid="demo-line"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="demo-lines-empty"]').text()).toBe('No lines yet');
  });
});
