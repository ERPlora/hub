// The menu an app of the Hub declares in its apps.py (`navigation = [Nav(...), …]`), for the tests that hold an app's
// routes to it and the pages that paint its tabs: each entry's id, English label, icon, path and the permission that
// opens it, in order. An entry is written by position (`Nav("id", _("Label"), "icon", "/path", permission="…")`) or by
// name, on one line or over several.
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { SessionMe, SessionMenuSection } from '@erplora/ui/shell';

/** The hub's root: base/frontend/__tests__ is three levels down. */
const HUB = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
/** The arguments of `Nav` by position. */
const POSITIONS = ['id', 'label', 'icon', 'path'];
const OPENING = '([{';
const CLOSING = ')]}';

export interface MenuEntry {
  id: string;
  /** The English label, the source of its translations. */
  label: string;
  icon: string;
  path: string;
  /** The permission that opens the entry (`live.E025` asks every module's entry for one). */
  permission: string | undefined;
}

/** The menu of `source`, the text of an apps.py; none without `navigation`. */
export function menuOf(source: string): MenuEntry[] {
  const start = source.search(/^\s+navigation = \[/m);
  if (start < 0) return [];
  const open = source.indexOf('[', start);
  return navCalls(source.slice(open + 1, closing(source, open))).map(entryOf);
}

/** The menu of the Hub's app `app` (its label). */
export function appMenu(app: string): MenuEntry[] {
  return menuOf(appsPy(app));
}

/**
 * The menu `base.session.me` gives whoever holds `permissions` (the superuser's `*` included) in the app `app`: its
 * entries they may open, in English and in order, under the app's name; none when they open none of them.
 */
export function openMenu(app: string, permissions: readonly string[]): SessionMenuSection[] {
  const opens = (permission: string | undefined) =>
    permission !== undefined && (permissions.includes('*') || permissions.includes(permission));
  const items = appMenu(app)
    .filter((entry) => opens(entry.permission))
    .map(({ path, label, icon }) => ({ path, label, icon }));
  if (!items.length) return [];
  const name = /^\s+verbose_name = (.+)$/m.exec(appsPy(app));
  return [{ id: app, label: translatable(name?.[1]), items }];
}

/** `me` with the menu its own permissions open in the app `app`, as a page of that app gets it from the server. */
export function withMenu(app: string, me: SessionMe): SessionMe {
  return { ...me, menu: openMenu(app, me.permissions) };
}

/** `me` with only the first `count` entries of its menu open: a session that opens fewer screens than its permissions. */
export function withFirstEntries(me: SessionMe, count: number): SessionMe {
  return { ...me, menu: me.menu.map((section) => ({ ...section, items: section.items.slice(0, count) })) };
}

function appsPy(app: string): string {
  return readFileSync(join(HUB, 'apps', app, 'apps.py'), 'utf8');
}

/** Where the bracket at `open` closes, past what any string inside holds. */
function closing(text: string, open: number): number {
  let depth = 0;
  for (let at = open; at < text.length; at += 1) {
    if (text[at] === '"') at = text.indexOf('"', at + 1);
    else if (OPENING.includes(text[at])) depth += 1;
    else if (CLOSING.includes(text[at]) && --depth === 0) return at;
  }
  throw new Error(`${text[open]} at ${open} never closes`);
}

/** The arguments of each `Nav(…)` of a list, as written. */
function navCalls(list: string): string[] {
  const calls: string[] = [];
  for (let at = list.indexOf('Nav('); at >= 0; at = list.indexOf('Nav(', at)) {
    const end = closing(list, at + 3);
    calls.push(list.slice(at + 4, end));
    at = end;
  }
  return calls;
}

/** The arguments of a call split at its own commas, never at one inside a nested call or a string. */
function splitArguments(call: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let at = 0; at < call.length; at += 1) {
    if (call[at] === '"') at = call.indexOf('"', at + 1);
    else if (OPENING.includes(call[at])) depth += 1;
    else if (CLOSING.includes(call[at])) depth -= 1;
    else if (call[at] === ',' && depth === 0) {
      parts.push(call.slice(start, at));
      start = at + 1;
    }
  }
  parts.push(call.slice(start));
  return parts.map((part) => part.trim()).filter(Boolean);
}

function entryOf(call: string): MenuEntry {
  const given: Record<string, string> = {};
  splitArguments(call).forEach((argument, position) => {
    const named = /^([a-z_]+)=([\s\S]*)$/.exec(argument);
    given[named ? named[1] : POSITIONS[position]] = named ? named[2].trim() : argument;
  });
  const permission = given.permission === undefined ? undefined : text(given.permission);
  return { id: text(given.id), label: translatable(given.label), icon: text(given.icon), path: text(given.path), permission };
}

/** The English text of a translatable string: `_("Label")` or `pgettext_lazy("context", "Label")`. */
function translatable(call: string | undefined): string {
  const words = /"([^"]*)"\)$/.exec(call?.trim() ?? '');
  if (!words) throw new Error(`not a translatable string: ${call}`);
  return words[1];
}

/** The value of a string literal. */
function text(literal: string | undefined): string {
  const value = /^"([^"]*)"$/.exec(literal ?? '');
  if (!value) throw new Error(`not a string: ${literal}`);
  return value[1];
}
