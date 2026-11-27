// Every catalogue of the Hub's SPA, as `frontend/main.ts` loads them, for the guards that read all of them at once.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

type Messages = { [key: string]: string | Messages };

/** The Hub's root (this file is base/frontend/__tests__/). */
export const HUB = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

/** Every SPA catalogue of the Hub: `base/frontend/locale/<lang>.json` and `apps/<id>/frontend/locale/<lang>.json`. */
export function hubCatalogues(): string[] {
  const apps = readdirSync(join(HUB, 'apps'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => join(HUB, 'apps', entry.name, 'frontend', 'locale'));
  return [join(HUB, 'base', 'frontend', 'locale'), ...apps].flatMap((dir) => {
    let names: string[];
    try {
      names = readdirSync(dir);
    } catch {
      return [];
    }
    return names.filter((name) => /^[a-z]{2}\.json$/.test(name)).map((name) => join(dir, name));
  });
}

/** A catalogue flattened to «file › key» → message, so a finding names where it is. */
export function flattened(file: string): Map<string, string> {
  const out = new Map<string, string>();
  const walk = (messages: Messages, prefix: string): void => {
    for (const [key, value] of Object.entries(messages)) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (typeof value === 'string') out.set(`${relative(HUB, file)} › ${path}`, value);
      else walk(value, path);
    }
  };
  walk(JSON.parse(readFileSync(file, 'utf8')) as Messages, '');
  return out;
}
