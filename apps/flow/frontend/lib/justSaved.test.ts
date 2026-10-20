// An automation saved for the first time is opened again on its own address: the mark that says it was
// just saved is read there once (FLOW-F09: «Saved.» and the editor stays on it).
import { describe, expect, it } from 'vitest';

import { markSaved, takeSaved } from './justSaved';

describe('justSaved', () => {
  it('a mark is read once, and only for its automation', () => {
    markSaved('f1');
    expect(takeSaved('f2')).toBe(false);
    expect(takeSaved('f1')).toBe(true);
    expect(takeSaved('f1')).toBe(false);
  });
});
