import { describe, expect, it } from 'vitest';

import { mountTable } from '../__tests__/mount-table';
import FloorSkeleton from './FloorSkeleton.vue';

describe('FloorSkeleton', () => {
  it('stands for the plan while it loads: tables of both shapes, shimmering, named for a screen reader', async () => {
    const { wrapper } = await mountTable(FloorSkeleton);
    const root = wrapper.find('[data-testid="table-floor-loading"]');
    expect(root.attributes('role')).toBe('progressbar');
    expect(root.attributes('aria-label')).toBe('Loading the floor plan');
    const blocks = wrapper.findAll('ion-skeleton-text');
    expect(blocks).toHaveLength(8);
    expect(blocks.every((block) => (block.element as HTMLElement & { animated?: boolean }).animated === true)).toBe(true);
    expect(blocks.map((block) => block.classes().includes('floor-skeleton__table--round'))).toEqual([false, false, true, false, false, true, false, false]);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountTable(FloorSkeleton, { locale: 'es' });
    expect(wrapper.find('[data-testid="table-floor-loading"]').attributes('aria-label')).toBe('Cargando el plano de sala');
  });
});
