// When the hub stops serving the page, the live client reloads it; inside the installed app, the reload first asks
// whether the hub is gone, and a gone hub is forgotten instead (ERPlora/app HUB_APP-F05;
// base/frontend/lib/change-business.test.ts runs that check). Here, that the Hub's live client is given it.
import { describe, expect, it, vi } from 'vitest';

const gone = vi.hoisted(() => ({ reloadOrForgetGone: vi.fn(async () => {}) }));
vi.mock('../base/frontend/lib/change-business', () => gone);
vi.mock('@erplora/ui/shell', async () => (await import('./__tests__/main-boot')).shellModule());
vi.mock('@erplora/ui/sdk', async (importOriginal) => (await import('./__tests__/main-boot')).sdkModule(importOriginal));

import { createShell } from '@erplora/ui/shell';
import { createLiveClient } from '@erplora/ui/sdk';

import { embedPage, shellFakes } from './__tests__/main-boot';

embedPage();
vi.mocked(createShell).mockResolvedValue(shellFakes() as never);
const main = await import('./main');

describe('main.ts — a hub that stopped serving the page', () => {
  it('reloads through the check for a gone hub, not straight away', async () => {
    await main.boot({});
    const overrides = vi.mocked(createLiveClient).mock.calls.at(-1)![1]!;
    expect(gone.reloadOrForgetGone).not.toHaveBeenCalled();

    overrides.reload!();

    expect(gone.reloadOrForgetGone).toHaveBeenCalledOnce();
  });
});
