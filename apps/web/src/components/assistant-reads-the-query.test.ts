// The assistant drawer reads `hub.setup.status` (hub#373) — wiring, not layout.
//
// The hub's pattern for this (`views/dashboard-setup-checklist.test.ts`): read the SFC source and
// assert the contract. What it protects is that there is **one** source of configuration truth left:
// the assistant reads the query itself instead of being handed a paragraph a screen built for it,
// and the screen that opens the assistant no longer knows how to write that paragraph.
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const drawer = readFileSync(new URL('./AssistantDrawer.vue', import.meta.url), 'utf8');
const dashboard = readFileSync(new URL('../views/DashboardPage.vue', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../lib/shell.ts', import.meta.url), 'utf8');
const lib = readFileSync(new URL('../lib/setup-status.ts', import.meta.url), 'utf8');

/** Every source file of the shell except the tests themselves. */
function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...sources(path));
    else if (/\.(ts|vue)$/.test(entry) && !entry.endsWith('.test.ts')) out.push(path);
  }
  return out;
}

describe('there is no second source of configuration truth', () => {
  it('`seedSetupContext` is gone from the shell, not just unused', () => {
    const srcDir = fileURLToPath(new URL('..', import.meta.url));
    const guilty = sources(srcDir).filter((f) => readFileSync(f, 'utf8').includes('seedSetupContext'));

    expect(guilty, 'a paragraph built beside the query is the divergence hub#373 closed').toEqual([]);
  });

  it('and the module does not export it any more', async () => {
    const mod = await import('../lib/setup-status');

    expect(Object.keys(mod)).not.toContain('seedSetupContext');
    // `pendingSetups` was its feed: a second, parallel projection of the document kept alive for
    // «the surfaces that have not moved yet». There are none left.
    expect(Object.keys(mod)).not.toContain('pendingSetups');
    expect(lib).not.toContain('pendingSetups');
  });
});

describe('the drawer reads the query', () => {
  it('it takes the document from the one query, not prose from a screen', () => {
    expect(drawer).toContain("from '../lib/setup-status'");
    expect(drawer).toContain('setupStatus');
    expect(drawer).toContain('setupBriefing');
    expect(drawer).not.toContain('assistantSeed');
  });

  it('it re-reads it before answering: a briefing built from a stale document describes another hub', () => {
    expect(drawer).toContain('refreshSetupStatus');
  });

  it('the briefing goes in as the `system` turn — it is context, never a message from the user', () => {
    const send = drawer.slice(drawer.indexOf('async function send('), drawer.indexOf('/** Rellena'));
    expect(send).toContain("role: 'system'");
    expect(send).toContain('setupBriefing');
  });

  it('the quick chips are the query’s pending items, and only those', () => {
    expect(drawer).toContain('assistantTasks');
  });
});

describe('the screen opens the assistant, it does not write for it', () => {
  it('the panel opens it on the setup topic instead of handing it a paragraph', () => {
    expect(dashboard).toContain('openAssistantForSetup');
    expect(dashboard).not.toContain('openAssistantWithContext');
  });

  it('the shell carries the INTENT (which item), never the text', () => {
    expect(shell).toContain('assistantIntent');
    expect(shell).toContain('openAssistantForSetup');
    expect(shell).not.toContain('openAssistantWithContext');
    expect(shell).not.toContain('assistantSeed');
  });
});
