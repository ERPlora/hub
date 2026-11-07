// What the guardrails over the Hub's frontends read (money-grouping, quantity-format): the frontends (base's, each
// app's and, when asked, the shared `ui`), their sources (`.ts` and `.vue`, without tests, their helpers, declarations
// or builds), the code of each (a `.vue`, its `<script>` blocks at their own lines) and what a guard finds in them, as
// `<path>:<line>` by app.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** The hub's root: base/frontend/__tests__ is three levels down. */
export const HUB = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

/** A frontend a guard reads, by the name its findings are reported under. */
export interface Frontend {
  app: string;
  dir: string;
}

/** A piece of code a guard parses, and the lines of its file before it. */
export interface ScriptBlock {
  code: string;
  offset: number;
}

/** The code of `text` (the file `name`): a `.ts` whole; a `.vue`, each `<script>` block. */
export function scriptBlocks(text: string, name: string): ScriptBlock[] {
  if (!name.endsWith('.vue')) return [{ code: text, offset: 0 }];
  return [...text.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map((match) => ({
    code: match[1],
    offset: text.slice(0, (match.index ?? 0) + match[0].indexOf(match[1])).split('\n').length - 1,
  }));
}

/** The sources under `dir`: `.ts` and `.vue`, without tests, their helpers, declarations or builds. */
export function frontendSources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .flatMap((entry) => {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        return entry.name.startsWith('.') || ['node_modules', '__tests__', 'generated', 'dist'].includes(entry.name)
          ? []
          : frontendSources(path);
      }
      if (entry.name.endsWith('.test.ts') || entry.name.endsWith('.d.ts')) return [];
      return entry.name.endsWith('.ts') || entry.name.endsWith('.vue') ? [path] : [];
    })
    .sort();
}

/** base's frontend, the shared `ui`'s (when `ui`) and each app's. */
export function hubFrontends({ ui }: { ui: boolean }): Frontend[] {
  const apps = readdirSync(join(HUB, 'apps'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({ app: entry.name, dir: join(HUB, 'apps', entry.name, 'frontend') }));
  const shared = ui ? [{ app: 'ui', dir: join(HUB, 'packages', 'ui', 'src') }] : [];
  return [{ app: 'base', dir: join(HUB, 'base', 'frontend') }, ...shared, ...apps];
}

/** The lines `find` gives for each source of `frontends`, as `<path>:<line>` from `root`, by app; a frontend that does
 *  not exist (an app without one) is skipped. */
export function findingsByApp(
  frontends: Frontend[],
  find: (text: string, file: string) => number[],
  root: string = HUB,
): Record<string, string[]> {
  const found: Record<string, string[]> = {};
  for (const { app, dir } of frontends) {
    let files: string[];
    try {
      files = frontendSources(dir);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue;
      throw error;
    }
    for (const file of files) {
      const where = relative(root, file);
      for (const line of find(readFileSync(file, 'utf8'), file)) (found[app] ??= []).push(`${where}:${line}`);
    }
  }
  return found;
}
