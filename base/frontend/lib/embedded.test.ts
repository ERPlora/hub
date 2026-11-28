import { describe, expect, it } from 'vitest';

import { readJsonBlock } from './embedded';

describe('readJsonBlock', () => {
  it('reads a JSON block Django embedded, and nothing when it is missing or broken', () => {
    document.body.innerHTML = `<script id="hub-home" type="application/json">{"name": "Bar"}</script>
      <script id="broken" type="application/json">{</script>`;
    expect(readJsonBlock<{ name: string }>('hub-home', document)).toEqual({ name: 'Bar' });
    expect(readJsonBlock('missing', document)).toBeUndefined();
    expect(readJsonBlock('broken', document)).toBeUndefined();
  });
});
