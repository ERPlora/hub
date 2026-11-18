// Motion that a device asked to reduce still plays unless the component turns it off. Every component of
// Tables that animates or transitions something says what it does under `prefers-reduced-motion: reduce`.
import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['../components/*.vue', '../components/*.css', '../pages/*.vue'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Whether `source` moves something (an animation or a transition that is not `none`) and never says what
 *  it does when the device asks for reduced motion. */
function ignoresReducedMotion(source: string): boolean {
  const moves = /(?:^|[\s;{])(?:animation|transition)(?:-[a-z-]+)?\s*:\s*(?!none\b)[^\s;]/m.test(source);
  return moves && !/@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)/.test(source);
}

describe('motion of Tables', () => {
  it('reads every page, component and stylesheet', () => {
    expect(Object.keys(sources)).toEqual(expect.arrayContaining(['./FloorCanvas.vue', './TableSheet.vue', '../pages/FloorPlanPage.vue']));
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(15);
  });

  it.each(Object.entries(sources))('%s turns its motion off when the device asks for reduced motion', (_, source) => {
    expect(ignoresReducedMotion(source)).toBe(false);
  });

  it('catches motion without a reduced-motion rule', () => {
    expect(ignoresReducedMotion('.a {\n  transition: opacity 160ms;\n}')).toBe(true);
    expect(ignoresReducedMotion('.a { animation: pulse 1s infinite; }')).toBe(true);
    expect(ignoresReducedMotion('.a {\n  transition: opacity 160ms;\n}\n@media (prefers-reduced-motion: reduce) {\n  .a { transition: none; }\n}')).toBe(false);
    expect(ignoresReducedMotion('.a { --ep-transition: 150ms ease; color: red; }')).toBe(false);
    expect(ignoresReducedMotion('.a { animation: none; }')).toBe(false);
  });
});
