// tables#56: an outlined field without `mode="md"` paints nothing in iOS mode (the old floor plan's «Add zone»
// stayed disabled behind an invisible input). Every `ion-input`, `ion-select` and `ion-textarea` of Tables with
// `fill="outline"` says `mode="md"`.
import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['../components/*.vue', '../pages/*.vue'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** The opening tags of the outlined fields of a template that do not say `mode="md"`. */
function unpainted(source: string): string[] {
  const tags = source.match(/<ion-(?:input|select|textarea)\b[^>]*>/g) ?? [];
  return tags.filter((tag) => /\bfill="outline"/.test(tag) && !/\bmode="md"/.test(tag));
}

describe('outlined fields of Tables', () => {
  it('reads every page and component', () => {
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(15);
  });

  it.each(Object.entries(sources))('%s outlines a field only in md mode', (_, source) => {
    expect(unpainted(source)).toEqual([]);
  });

  it('catches an outlined field without md mode', () => {
    expect(unpainted('<ion-input\n  fill="outline"\n  label="Name"\n/>')).toHaveLength(1);
    expect(unpainted('<ion-input fill="outline" mode="md" />')).toEqual([]);
  });
});
