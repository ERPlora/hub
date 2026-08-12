import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

// Every `<ion-*>` a template paints must be IMPORTED by that template (hub#797).
//
// The failure this catches is one that looks like success. Ionic ships each component twice: as a
// Vue component you import, and as a custom element `defineCustomElements` registers on the
// document. Forget the import and Vue cannot resolve the tag, shrugs, and hands it to the browser
// as an unknown element — which the custom element definition then upgrades. The button appears,
// it works, and the only trace is a `[Vue warn]: Failed to resolve component: ion-button` on every
// single load.
//
// Two reasons that is not cosmetic. The console fills with a warning nobody can act on, so the
// warning that MATTERS during QA scrolls past unread — this is the same class of noise that let the
// broken icon of hub#793 sit in production. And the tag stops going through Ionic's Vue layer: the
// prop casing, the `v-model` bridges and the event names it normalises are simply not applied, so
// the component behaves like whatever the raw custom element happens to do today. It works until
// a Vue or Ionic upgrade decides otherwise, and then it breaks with no diff to blame.
//
// The guard is repo-wide and not just the two components the issue named, because the defect is
// «somebody adds a tag and forgets the import», and that somebody will be working on a third file.
const SRC = fileURLToPath(new URL('.', import.meta.url));

/** `ion-split-pane` → `IonSplitPane`: the name the SFC has to import. */
function vueComponentName(tag: string): string {
  return tag
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('');
}

/**
 * The whole `<template>` block of an SFC.
 *
 * From the FIRST `<template` to the LAST `</template>`, on purpose: `<template #footer>` and
 * `<template v-if>` are ordinary inside a Vue template, so stopping at the first close would leave
 * most of the markup unscanned — and unscanned is exactly where a missing import hides.
 */
function templateOf(source: string): string {
  const open = source.indexOf('<template');
  const close = source.lastIndexOf('</template>');
  if (open === -1 || close === -1 || close < open) return '';
  return source.slice(open, close);
}

/** What the SFC pulls in from `@ionic/vue` (controllers included; harmless, they are not tags). */
function ionicImports(source: string): Set<string> {
  const names = new Set<string>();
  const pattern = /import\s*\{([^}]*)\}\s*from\s*['"]@ionic\/vue['"]/g;
  for (const match of source.matchAll(pattern)) {
    for (const raw of match[1].split(',')) {
      // `IonButton as Button` — what has to be registered is the local name Vue resolves.
      const name = raw.trim().split(/\s+as\s+/).pop()?.trim();
      if (name) names.add(name);
    }
  }
  return names;
}

function sfcFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      out.push(...sfcFiles(path));
      continue;
    }
    if (entry.endsWith('.vue')) out.push(path);
  }
  return out;
}

describe('a template never paints an Ionic component it did not import', () => {
  it('every <ion-*> tag in every SFC has its import', () => {
    const offenders: string[] = [];

    for (const path of sfcFiles(SRC)) {
      const source = readFileSync(path, 'utf8');
      const template = templateOf(source);
      if (!template) continue;

      const imported = ionicImports(source);
      const tags = new Set(
        [...template.matchAll(/<(ion-[a-z0-9-]+)/g)].map((match) => match[1]),
      );

      for (const tag of [...tags].sort()) {
        if (imported.has(vueComponentName(tag))) continue;
        const line = source.split('\n').findIndex((l) => l.includes(`<${tag}`)) + 1;
        offenders.push(`${path.slice(SRC.length)}:${line} → <${tag}> needs ${vueComponentName(tag)}`);
      }
    }

    // Named one per line: when this fails, the message IS the list of imports to add.
    expect(offenders.join('\n')).toBe('');
  });
});
