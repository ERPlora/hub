// @vitest-environment node
// Lint of hub-next: the SPA reaches the server only through the SDK (`@erplora/ui/sdk`), so the
// shell entry and every app frontend are linted for raw network globals. Linted for real here.
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

const eslint = new ESLint({ cwd: dirname(fileURLToPath(import.meta.url)) });

async function restricted(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter((m) => m.ruleId === 'no-restricted-globals').map((m) => m.message);
}

// The first lint loads ESLint's parsers and plugins from the disk, so its time is the machine's: with several test
// runs on one machine (load 20–40) and every opened file scanned, it took up to 5.7 s (2026-10-21), against
// Vitest's 5 s. 60 s for whichever test lints first, as the guardrails that read the whole tree (tsconfig.test.ts).
describe('eslint config', { timeout: 60_000 }, () => {
  it.each(['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest'])('forbids %s in an app page and in the entry', async (name) => {
    const code = `export const x = ${name};\n`;
    expect(await restricted(code, 'apps/demo/frontend/pages/ItemListPage.ts')).toHaveLength(1);
    expect(await restricted(code, 'frontend/main.ts')).toHaveLength(1);
  });

  it('forbids it in the <script setup> of a .vue page too', async () => {
    const code = `<script setup lang="ts">\nconst items = fetch('/api/demo/items');\n</script>\n<template><div>{{ items }}</div></template>\n`;
    expect(await restricted(code, 'apps/demo/frontend/pages/ItemListPage.vue')).toEqual([
      "Unexpected use of 'fetch'. Network access goes through the SDK (@erplora/ui/sdk).",
    ]);
  });

  it('takes slot="…" on ion-* and on HubIcon as the Web Components slot, not on a leftover ok-*', async () => {
    const slotted = async (tag: string) => {
      const code = `<template><ion-button><${tag} slot="start" /></ion-button></template>\n`;
      const [result] = await eslint.lintText(code, { filePath: 'apps/demo/frontend/pages/Probe.vue' });
      return result.messages.filter((m) => m.ruleId === 'vue/no-deprecated-slot-attribute').length;
    };
    expect(await slotted('ion-icon')).toBe(0);
    expect(await slotted('HubIcon')).toBe(0);
    expect(await slotted('ok-icon')).toBe(1); // OutfitKit is gone (PLAN §16.11): no exception left for it
  });

  it('ignores the build and collectstatic output, the virtualenv, and the live and ui submodules', async () => {
    expect(await eslint.isPathIgnored('frontend/dist/assets/main-abc.js')).toBe(true);
    expect(await eslint.isPathIgnored('staticfiles/admin/js/core.js')).toBe(true);
    // The repo's own .venv (uv) carries the admin's JavaScript.
    expect(await eslint.isPathIgnored('.venv/lib/python3.14/site-packages/django/contrib/admin/static/admin/js/core.js')).toBe(true);
    // packages/ui and packages/live are linted in their own repos.
    expect(await eslint.isPathIgnored('packages/ui/src/sdk/client.ts')).toBe(true);
  });
});
