// The translations the master QA of the Hub checks on screen (BASE-G152, base-qa-master.spec.ts). The hub writes in
// English and translates to Spanish: the SPA's catalogues (`<…>/locale/{en,es}.json` of base and of each app,
// `packages/ui/src/**/locales/{en,es}.json` of the shell and its components) and Django's (`locale/es/LC_MESSAGES/
// django.po`, the apps' names, menus and server messages). A text on screen that only the other language's catalogue has
// is a text left untranslated; a message key on screen (`base.apps.add`) is one the catalogue lacks.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

export type Language = 'en' | 'es';
export type Pair = [en: string, es: string];

/** The texts each language alone writes: neither the same in both nor written by the other anywhere. */
export interface Catalog {
  en: Set<string>;
  es: Set<string>;
}

/** Folders a checkout keeps that are no catalogue of the hub. */
const SKIPPED = new Set(['node_modules', '.venv', '.git', 'dist', '.artifacts', 'generated', '__pycache__', 'staticfiles']);

/** A text with a value still to put in (`{name}`, `%(count)s`, `%s`): on screen it never reads as written. */
const PLACEHOLDER = /\{[^}]*\}|%(\([^)]*\))?[sd]/;

/** A message key: three or more dotted words, each starting with a letter, nothing else (no `@`, no spaces). */
const KEY = /^[a-z][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*){2,}$/;

/** A `.po` string's text, its escapes undone. */
function unquote(text: string): string {
  return text.replace(/\\(["\\nt])/g, (_, c: string) => ({ '"': '"', '\\': '\\', n: '\n', t: '\t' })[c] ?? c);
}

/** The translated pairs of a `.po`: its header, an empty msgstr and a fuzzy entry left out; a plural, both forms. */
export function poPairs(po: string): Pair[] {
  const pairs: Pair[] = [];
  for (const entry of po.split(/\n\s*\n/)) {
    const lines = entry.split('\n');
    if (lines.some((line) => line.startsWith('#,') && line.includes('fuzzy'))) continue;
    const fields = new Map<string, string>();
    let field = '';
    for (const line of lines) {
      const start = /^(msgid|msgid_plural|msgstr(?:\[\d+\])?) "(.*)"$/.exec(line);
      if (start) {
        field = start[1];
        fields.set(field, unquote(start[2]));
      } else if (field && /^".*"$/.test(line)) {
        fields.set(field, fields.get(field)! + unquote(line.slice(1, -1)));
      }
    }
    const forms: [string | undefined, string | undefined][] = fields.has('msgid_plural')
      ? [
          [fields.get('msgid'), fields.get('msgstr[0]')],
          [fields.get('msgid_plural'), fields.get('msgstr[1]')],
        ]
      : [[fields.get('msgid'), fields.get('msgstr')]];
    for (const [en, es] of forms) if (en && es) pairs.push([en, es]);
  }
  return pairs;
}

/** The texts under the same key of the English and the Spanish catalogue of the SPA. */
export function jsonPairs(en: unknown, es: unknown): Pair[] {
  if (typeof en === 'string') return typeof es === 'string' ? [[en, es]] : [];
  if (en === null || typeof en !== 'object' || es === null || typeof es !== 'object') return [];
  const translated = es as Record<string, unknown>;
  return Object.entries(en as Record<string, unknown>).flatMap(([key, value]) => jsonPairs(value, translated[key]));
}

/** The texts of one language only, from every pair of the catalogues; never a single letter (an initial, a day's). */
export function catalogOf(pairs: Pair[]): Catalog {
  const plain = pairs.filter(([en, es]) => !PLACEHOLDER.test(en) && !PLACEHOLDER.test(es) && en.length > 1 && es.length > 1);
  const allEn = new Set(plain.map(([en]) => en));
  const allEs = new Set(plain.map(([, es]) => es));
  const differ = plain.filter(([en, es]) => en !== es);
  return {
    en: new Set(differ.map(([en]) => en).filter((en) => !allEs.has(en))),
    es: new Set(differ.map(([, es]) => es).filter((es) => !allEn.has(es))),
  };
}

/** A text as a person reads it: its spaces, non-breaking ones too, collapsed, and trimmed. */
export function normalText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

/** The texts, once each, that only the other language writes: untranslated in a screen in `language`. */
export function wrongLanguage(texts: string[], language: Language, catalog: Catalog): string[] {
  const other = language === 'es' ? catalog.en : catalog.es;
  return [...new Set(texts.map(normalText))].filter((text) => other.has(text));
}

/** The texts, once each, that are a message key and not a message. */
export function rawKeys(texts: string[]): string[] {
  return [...new Set(texts.map(normalText))].filter((text) => KEY.test(text));
}

/** Every file under `dir` whose path ends with `suffix`, outside the folders that are no catalogue. */
function filesUnder(dir: string, suffix: string): string[] {
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return [];
  }
  return names.flatMap((name) => {
    if (SKIPPED.has(name)) return [];
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return filesUnder(path, suffix);
    return path.endsWith(suffix) ? [path] : [];
  });
}

const json = (path: string): unknown => JSON.parse(readFileSync(path, 'utf8'));

/** The hub's catalogues under the checkout `root`: the SPA's JSON pairs and Django's `.po`. */
export function loadCatalog(root: string): Catalog {
  const spa = filesUnder(root, 'en.json')
    .filter((path) => /\/locales?\/en\.json$/.test(path))
    .flatMap((path) => {
      const es = path.replace(/en\.json$/, 'es.json');
      // A catalogue with no Spanish twin has nothing to compare.
      return existsSync(es) ? jsonPairs(json(path), json(es)) : [];
    });
  const django = filesUnder(root, join('locale', 'es', 'LC_MESSAGES', 'django.po')).flatMap((path) =>
    poPairs(readFileSync(path, 'utf8')),
  );
  return catalogOf([...spa, ...django]);
}
