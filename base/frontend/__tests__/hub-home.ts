// The `hub-home` block `base/spa.py` embeds in the page (`readJsonBlock`, lib/home.ts), as a test puts it there and takes
// it away: with what a test needs of it, or none at all; and after each test, no block and a browser again.
import { applySurface } from '@erplora/ui/shell';

import type { HubHome } from '../lib/home';

export function embedHubHome(block: Partial<HubHome> | null): void {
  document.head.innerHTML = block
    ? `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>`
    : '';
}

export function forgetHubHome(): void {
  applySurface('web');
  document.head.innerHTML = '';
}
