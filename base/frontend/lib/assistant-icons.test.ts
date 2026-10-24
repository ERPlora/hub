// The four icons of the assistant's composer that the shell does not register yet (UI-REQUESTS.md): baked into the
// bundle as the shell bakes its own, never fetched (CSP: nothing but `data:`).
import { describe, expect, it } from 'vitest';

import { ASSISTANT_ICONS } from './assistant-icons';

describe('ASSISTANT_ICONS', () => {
  it('are SVG baked as data: URLs, one for each control', () => {
    expect(Object.keys(ASSISTANT_ICONS).sort()).toEqual(['attach', 'listen', 'mic', 'stop']);
    for (const url of Object.values(ASSISTANT_ICONS)) {
      expect(url.startsWith('data:image/svg+xml;utf8,<svg')).toBe(true);
    }
  });
});
