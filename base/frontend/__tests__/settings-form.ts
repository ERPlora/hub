// What the tests of every settings page check the same way (hub#867, hub#897, hub#982, hub#1237): the page builds its
// form on `useSettingsForm`, paints its number fields with `SettingsNumberField`, ends it with `SettingsFormFooter`
// (@erplora/ui/components) and never lets the browser judge it (`novalidate`), so where the save's notices sit, what
// Enter in a field does and what a refused field shows are read alike in every app. `settingsForms` gives the guards
// the sources of those forms, and `openingTags` the tags of a template they look at.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { flush } from '../../../packages/ui/src/sdk/__tests__/live-harness';

const HUB = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const APPS = join(HUB, 'apps');

/** Every `.vue` below `dir`, without `node_modules` and the tests' own folders. */
function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === 'node_modules' || entry.name === '__tests__' ? [] : vueFiles(path);
    return entry.name.endsWith('.vue') ? [path] : [];
  });
}

/** The `.vue` files of the apps' frontends whose script builds its form with `useSettingsForm` (tests and their
 *  helpers left out), relative to the hub, with their source. */
export function settingsForms(): { file: string; source: string }[] {
  return readdirSync(APPS, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .flatMap((app) => {
      const frontend = join(APPS, app.name, 'frontend');
      try {
        return vueFiles(frontend);
      } catch {
        return []; // An app without a frontend.
      }
    })
    .map((path) => ({ file: relative(HUB, path), source: readFileSync(path, 'utf8') }))
    .filter(({ source }) => /\buseSettingsForm\s*\(/.test(source));
}

/** Each opening tag of `source` named one of `names`, as written (`ion-input` or `IonInput`), up to the `>` that closes
 *  it: a `<` or a `>` inside a quoted attribute is the attribute's, and a longer name (`<ion-input-otp`, `<formula`)
 *  is another tag. */
export function openingTags(source: string, names: readonly string[]): string[] {
  const tag = new RegExp(`<(?:${names.join('|')})(?=[\\s/>])(?:"[^"]*"|'[^']*'|[^>"'])*>`, 'g');
  return [...source.matchAll(tag)].map(([found]) => found);
}

/** Whether `middle` comes after `first` and before `last` on the page. */
export function between(first: Element, middle: Element, last: Element): boolean {
  return (
    !!(first.compareDocumentPosition(middle) & Node.DOCUMENT_POSITION_FOLLOWING) &&
    !!(middle.compareDocumentPosition(last) & Node.DOCUMENT_POSITION_FOLLOWING)
  );
}

/** Enter in a field of the settings form `form`: Ionic puts a hidden submit button in it, so the form is submitted;
 *  then the save lands. */
export async function pressEnter(form: Element | null | undefined): Promise<void> {
  if (!form) throw new Error('no settings form to submit');
  form.dispatchEvent(new Event('submit', { cancelable: true }));
  await flush();
  await flush();
}

/** What a refusal shows: whether the red notice above «Save» is on screen (`notice`, the page's own probe), and each
 *  refused field's message under it (`says`) and its red mark (`marked`). */
export function refusalMarks(field: (name: string) => Element & { errorText?: string }, notice: () => boolean) {
  return {
    notice,
    says: (name: string): string => field(name).errorText ?? '',
    marked: (name: string): boolean => field(name).classList.contains('ion-invalid'),
  };
}
