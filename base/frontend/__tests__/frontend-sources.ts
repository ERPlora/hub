// What the guardrails over the Hub's frontends read (money-grouping, quantity-format, decimal-mark): the frontends
// (base's, each app's and, when asked, the shared `ui`), their sources (`.ts` and `.vue`, without tests, their helpers,
// declarations or builds), the code of each (a `.vue`, its `<script>` blocks at their own lines) and what a guard finds
// in them, as `<path>:<line>` by app; and, for the guards that parse the code (TypeScript's AST), `linesWhere`, the
// lines of the nodes a guard looks for, and `bare`, which they read an expression with. The frontends are listed and
// read without holding the worker (hub#1315): some 2,000 files, and on a loaded machine each first open waits on its own.
import { readdirSync } from 'node:fs';
import { readdir } from 'node:fs/promises';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';

import { readTexts } from '../../../vitest.offload';

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

/** `node` without the parentheses, `as` and `satisfies` around it. */
export function bare(node: ts.Expression): ts.Expression {
  let current = node;
  while (ts.isParenthesizedExpression(current) || ts.isAsExpression(current) || ts.isSatisfiesExpression(current)) {
    current = current.expression;
  }
  return current;
}

/** The code of `text` (the file `name`): a `.ts` whole; a `.vue`, each `<script>` block. */
export function scriptBlocks(text: string, name: string): ScriptBlock[] {
  if (!name.endsWith('.vue')) return [{ code: text, offset: 0 }];
  return [...text.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map((match) => ({
    code: match[1],
    offset: text.slice(0, (match.index ?? 0) + match[0].indexOf(match[1])).split('\n').length - 1,
  }));
}

/** The lines of `text` (the file `name`: a `.ts`, or a `.vue` whose `<script>` blocks are read) of each node of its code
 *  `holds` is true of, at their own lines of the file. */
export function linesWhere(text: string, name: string, holds: (node: ts.Node) => boolean): number[] {
  return scriptBlocks(text, name).flatMap(({ code, offset }) => {
    const file = ts.createSourceFile(name.endsWith('.vue') ? `${name}.ts` : name, code, ts.ScriptTarget.Latest, true);
    const lines: number[] = [];
    const visit = (node: ts.Node): void => {
      if (holds(node)) lines.push(file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1 + offset);
      ts.forEachChild(node, visit);
    };
    visit(file);
    return lines;
  });
}

/** The sources under `dir`: `.ts` and `.vue`, without tests, their helpers, declarations or builds. Each folder is
 *  listed by Node's own pool of threads, all of a level at once. */
export async function frontendSources(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  const found = await Promise.all(
    entries.map((entry): string[] | Promise<string[]> => {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        return entry.name.startsWith('.') || ['node_modules', '__tests__', 'generated', 'dist'].includes(entry.name)
          ? []
          : frontendSources(path);
      }
      if (entry.name.endsWith('.test.ts') || entry.name.endsWith('.d.ts')) return [];
      return entry.name.endsWith('.ts') || entry.name.endsWith('.vue') ? [path] : [];
    }),
  );
  return found.flat().sort();
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
 *  not exist (an app without one) is skipped. The sources are listed and read at once, without holding the worker
 *  (`readTexts`); what is left here is `find`'s own work, file by file. */
export async function findingsByApp(
  frontends: Frontend[],
  find: (text: string, file: string) => number[],
  root: string = HUB,
): Promise<Record<string, string[]>> {
  const sources = await Promise.all(
    frontends.map(async ({ app, dir }) => {
      try {
        return { app, files: await frontendSources(dir) };
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { app, files: [] };
        throw error;
      }
    }),
  );
  const texts = await readTexts(sources.flatMap(({ files }) => files));
  const found: Record<string, string[]> = {};
  let index = 0;
  for (const { app, files } of sources) {
    for (const file of files) {
      const where = relative(root, file);
      for (const line of find(texts[index++], file)) (found[app] ??= []).push(`${where}:${line}`);
    }
  }
  return found;
}
