// @vitest-environment node
// Guardrail of the windows' fields (hub#888): FormModal (@erplora/ui) takes a mark away from the refused field a
// person corrects, and it tells that field by its `name` when the name is a key of the refusal; without one it
// falls back to the words the field shows, and two fields refused with the same words («Enter a whole number.» under
// the year and the next number of a new series) are not told apart: correcting one leaves both marked. So every field
// of a FormModal window that paints the window's refusal (`:error-text="fieldErrors.<k>"`) carries `name="<k>"`; one
// that paints `fieldErrors[<expr>]` carries `:name="<expr>"`; one that paints it some other way
// (`errorOf(fieldErrors, index, 'price')`) carries a `name` of its own. The same holds in a component the window hands
// its refusal to (`:field-errors="fieldErrors"`), followed to its file. A refusal the window paints apart from any field
// (`<p v-if="fieldErrors.tiers">`, `{{ fieldErrors.customer }}`) needs a control named after its key too, or FormModal
// never hears it corrected and the line stays until the next save: the field it is about (`name="is_default"` on the
// toggle) or the group's `<fieldset ref="tiersGroup" name="tiers">`, whose ref goes to `useGroupChange('tiersGroup')`
// (a fieldset says no change of its own). Nor does any FormModal window, whether it takes `fieldErrors` or not, read
// the refusal it hands FormModal raw in its script (`error.value?.fields`): what it paints from there is the server's
// word as it came, which no correction takes away; it reshapes the refusal before handing it over, if it must, and
// paints `fieldErrors`. The files still waiting are listed below with how many they leave unnamed or read raw; the
// number only goes down, and a fixed file leaves the list.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';
import { parse } from 'vue/compiler-sfc';

/** The root of the hub: the paths below are relative to it. */
const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

/** What is left of the fields without their name, by file: it only goes down. A component around a field (Combo of
 *  @erplora/ui, ServicesField) has to hand its `name` to its ion-input, as Combo does: FormModal reads the `name`
 *  property of the field, not an attribute on a wrapper's div, so a name this guard sees there fixes nothing until
 *  the component declares it; the window's own test (`itTellsTheCorrectedFieldApart`) is what proves it. */
const STILL_UNNAMED: Record<string, number> = {
  'apps/service/frontend/components/CategoryFormModal.vue': 3,
  'apps/service/frontend/components/GrantAdjustModal.vue': 3,
  'apps/service/frontend/components/GrantVoidModal.vue': 1,
  'apps/service/frontend/components/PackageFormModal.vue': 9,
  'apps/service/frontend/components/ServiceFormModal.vue': 6,
};

/** What is left of the raw reads of a window's refusal in windows that do not take `fieldErrors`, by file: it only goes
 *  down. */
const STILL_READ_RAW: Record<string, number> = {
  'apps/printing/frontend/components/DeviceModal.vue': 1,
  'apps/printing/frontend/components/PrinterModal.vue': 1,
};

/** Windows that take away themselves a refusal they paint apart, once the person changes what it is about, rather than
 *  through FormModal hearing a control of its name: by file, those keys. This guard cannot see that; the window's own
 *  test proves each, and an entry the tree no longer needs leaves. */
const TAKEN_AWAY_BY_THE_WINDOW: Record<string, readonly string[]> = {
  'apps/whatsapp_inbox/frontend/components/TemplateFormModal.vue': ['buttons', 'header_sample'],
};

// ── Reading a template ──────────────────────────────────────────────────────────────────────────────────────────────

/** The few shapes of Vue's template tree this guard reads (`@vue/compiler-core`'s node types 1, 6 and 7). */
interface Attribute {
  type: 6;
  name: string;
  value?: { content: string };
}
interface Directive {
  type: 7;
  name: string;
  arg?: { content?: string };
  exp?: { content?: string };
}
interface Element {
  type: 1;
  tag: string;
  props: (Attribute | Directive)[];
  children: TemplateNode[];
  loc: { start: { line: number } };
}
interface Interpolation {
  type: 5;
  content: { content?: string };
  loc: { start: { line: number } };
}
type TemplateNode = Element | { type: number; children?: unknown };

const ELEMENT = 1;
const INTERPOLATION = 5;
const ATTRIBUTE = 6;
const DIRECTIVE = 7;

const isElement = (node: TemplateNode): node is Element => node.type === ELEMENT;
const squeeze = (text: string): string => text.replace(/\s+/g, '');
const camelize = (text: string): string => text.replace(/-(\w)/g, (_, letter: string) => letter.toUpperCase());
const pascalize = (text: string): string => camelize(text).replace(/^\w/, (letter) => letter.toUpperCase());

/** `element`'s bound value of `prop` (`:prop`, `v-bind:prop`, also camelCased), or nothing. */
function bound(element: Element, prop: string): string | undefined {
  const names = new Set([prop, camelize(prop)]);
  for (const p of element.props) {
    if (p.type === DIRECTIVE && p.name === 'bind' && p.arg?.content && names.has(p.arg.content)) return p.exp?.content?.trim();
  }
  return undefined;
}

/** `element`'s plain `name="…"`, or nothing. */
function plainName(element: Element): string | undefined {
  for (const p of element.props) if (p.type === ATTRIBUTE && p.name === 'name') return p.value?.content ?? '';
  return undefined;
}

/** The text a bound `:name` evaluates to when it is a literal (`'year'`, `"year"`, `` `year` `` with no `${`). */
function literal(expression: string): string | undefined {
  const match = /^(['"`])([^'"`$]*)\1$/.exec(expression.trim());
  return match?.[2];
}

function walk(nodes: readonly TemplateNode[], visit: (element: Element) => void): void {
  for (const node of nodes) {
    if (!isElement(node)) continue;
    visit(node);
    walk(node.children, visit);
  }
}

/** What is wrong with `element`'s name, when it paints the refusal held in `refusal` (`fieldErrors`), else nothing. */
function unnamed(element: Element, refusal: string): string | undefined {
  const shown = bound(element, 'error-text');
  if (shown === undefined || !new RegExp(`\\b${refusal}\\b`).test(shown)) return undefined;
  const plain = plainName(element);
  const dynamic = bound(element, 'name');
  const name = plain ?? (dynamic !== undefined ? literal(dynamic) : undefined);
  const key = new RegExp(`^${refusal}\\??\\.(\\w+)$`).exec(squeeze(shown))?.[1];
  if (key !== undefined) return name === key ? undefined : `paints ${shown} without name="${key}"`;
  const index = new RegExp(`^${refusal}\\??\\.?\\[([^\\]]+)\\]$`).exec(squeeze(shown))?.[1];
  if (index !== undefined) {
    const named = dynamic !== undefined ? squeeze(dynamic) === index : literal(index) !== undefined && plain === literal(index);
    return named ? undefined : `paints ${shown} without :name="${index}"`;
  }
  return plain || dynamic ? undefined : `paints ${shown} without a name`;
}

/** A refusal a window paints apart from any field: where, and under which key. */
interface Notice {
  key: string;
  line: number;
  tag: string;
  shown: string;
}

/** The directives a node is painted on. */
const CONDITIONS = new Set(['if', 'else-if', 'show']);

/** Each key of the refusal that `reach` paints in an element of its own (`<p v-if="fieldErrors.tiers">`, or
 *  `{{ fieldErrors.tiers }}` in any element) rather than in a field's `:error-text`, once, where it first does. */
function paintedApart(reach: Reach): Notice[] {
  const found = new Map<string, Notice>();
  const note = (expression: string | undefined, line: number, tag: string): void => {
    for (const [shown, key] of (expression ?? '').matchAll(new RegExp(`\\b${reach.refusal}\\??\\.(\\w+)`, 'g'))) {
      if (!found.has(key)) found.set(key, { key, line, tag, shown });
    }
  };
  const visit = (nodes: readonly TemplateNode[], parent: Element | undefined): void => {
    for (const node of nodes) {
      if (node.type === INTERPOLATION && parent) {
        const { content, loc } = node as Interpolation;
        note(content.content, loc.start.line, parent.tag);
      }
      if (!isElement(node)) continue;
      if (bound(node, 'error-text') === undefined) {
        for (const p of node.props) if (p.type === DIRECTIVE && CONDITIONS.has(p.name)) note(p.exp?.content, node.loc.start.line, node.tag);
      }
      visit(node.children, node);
    }
  };
  visit(reach.nodes, undefined);
  return [...found.values()];
}

/** The plain HTML fields FormModal hears change under their `name`; on a div or a section it reads none. */
const TYPED_HTML = new Set(['input', 'select', 'textarea']);
/** The plain HTML elements whose `name` FormModal reads but that never say a change themselves: a group's `<fieldset>`
 *  counts once the window hands its ref to `useGroupChange`, which says each change for it. */
const MUTE_HTML = new Set(['button', 'fieldset', 'output']);

/** `element`'s plain `ref="…"`, or nothing. */
function plainRef(element: Element): string | undefined {
  for (const p of element.props) if (p.type === ATTRIBUTE && p.name === 'ref') return p.value?.content;
  return undefined;
}

/** The names the controls in `nodes` carry, plainly or as a literal (an Ionic field, a component, a plain HTML field, a
 *  group whose ref is in `voiced`), and apart the groups that say no change, by name, with their tag. */
function controlNames(nodes: readonly TemplateNode[], voiced: ReadonlySet<string>): { heard: Set<string>; mute: Map<string, string> } {
  const heard = new Set<string>();
  const mute = new Map<string, string>();
  walk(nodes, (element) => {
    const dynamic = bound(element, 'name');
    const name = plainName(element) ?? (dynamic !== undefined ? literal(dynamic) : undefined);
    if (!name) return;
    if (MUTE_HTML.has(element.tag)) {
      if (voiced.has(plainRef(element) ?? '')) heard.add(name);
      else if (!mute.has(name)) mute.set(name, element.tag);
    } else if (TYPED_HTML.has(element.tag) || element.tag.includes('-') || /^[A-Z]/.test(element.tag)) heard.add(name);
  });
  return { heard, mute };
}

/** The refs a source's script hands to `useGroupChange('<ref>')`. */
function voicedGroups(script: string): Set<string> {
  return new Set([...script.matchAll(/\buseGroupChange\(\s*(['"`])(\w+)\1\s*\)/g)].map((match) => match[2]));
}

/** A source's components brought from a `.vue` file of the hub, by name: `{ RecipientFields: './RecipientFields.vue' }`. */
function vueImports(script: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const [, name, path] of script.matchAll(/\bimport\s+(\w+)\s+from\s*['"](\.{1,2}\/[^'"]+\.vue)['"]/g)) found[name] = path;
  return found;
}

/** A script block of a source: its text and the line of the file it starts on. */
interface Script {
  content: string;
  line: number;
}

/** A source's template tree, its scripts, the components it imports and the groups it voices, or nothing when it has
 *  no template. */
function read(source: string): { nodes: TemplateNode[]; scripts: Script[]; imports: Record<string, string>; voiced: Set<string> } | undefined {
  const { descriptor } = parse(source);
  const ast = descriptor.template?.ast as unknown as { children: TemplateNode[] } | undefined;
  if (!ast) return undefined;
  const scripts = [descriptor.script, descriptor.scriptSetup].flatMap((block) => (block ? [{ content: block.content, line: block.loc.start.line }] : []));
  const script = scripts.map((block) => block.content).join('\n');
  return { nodes: ast.children, scripts, imports: vueImports(script), voiced: voicedGroups(script) };
}

/** Where a window's refusal goes: the name its fields read it by (`fieldErrors`), the nodes that read it and the refs of
 *  the groups its file voices with `useGroupChange`. */
interface Reach {
  refusal: string;
  nodes: readonly TemplateNode[];
  voiced?: ReadonlySet<string>;
}

const isFormModal = (element: Element): boolean => element.tag === 'FormModal' || element.tag === 'form-modal';

/** The default slot of each FormModal in `nodes` that takes its `fieldErrors`, under the name it gives them. */
function windows(nodes: readonly TemplateNode[]): Reach[] {
  const found: Reach[] = [];
  const slotOf = (element: Element): Reach | undefined => {
    for (const p of element.props) {
      if (p.type !== DIRECTIVE || p.name !== 'slot' || (p.arg?.content ?? 'default') !== 'default') continue;
      const named = /\bfieldErrors\b(?:\s*:\s*(\w+))?/.exec(p.exp?.content ?? '');
      if (named) return { refusal: named[1] ?? 'fieldErrors', nodes: element.children };
    }
    return undefined;
  };
  walk(nodes, (element) => {
    if (!isFormModal(element)) return;
    const own = slotOf(element);
    if (own) found.push(own);
    for (const child of element.children) {
      const slot = isElement(child) && child.tag === 'template' ? slotOf(child) : undefined;
      if (slot) found.push(slot);
    }
  });
  return found;
}

/** What each FormModal in `nodes` hands as its refusal (`:error="error"`), whether its slot takes `fieldErrors` or not. */
function handedRefusals(nodes: readonly TemplateNode[]): string[] {
  const found = new Set<string>();
  walk(nodes, (element) => {
    const error = isFormModal(element) ? bound(element, 'error') : undefined;
    if (error) found.add(error);
  });
  return [...found];
}

/** What `read(file)` says about the hub's file at `path` (relative to the hub), or nothing for a file it cannot read. */
type Reader = (path: string) => string | undefined;

/** Every field without its name in `reach`, as `<file>:<line>: <tag> …`, following the refusal into the components it is
 *  handed to (`:field-errors="fieldErrors"`); each component file is followed once per prop. */
function unnamedFields(file: string, reach: Reach, imports: Record<string, string>, readFile: Reader, seen = new Set<string>()): string[] {
  const found: string[] = [];
  walk(reach.nodes, (element) => {
    const problem = unnamed(element, reach.refusal);
    if (problem) found.push(`${file}:${element.loc.start.line}: <${element.tag}> ${problem}`);
    for (const p of element.props) {
      if (p.type !== DIRECTIVE || p.name !== 'bind' || !p.arg?.content || p.exp?.content?.trim() !== reach.refusal) continue;
      if (camelize(p.arg.content) === 'errorText') continue;
      const path = imports[pascalize(element.tag)];
      const target = path ? relative(HUB_DIR, resolve(HUB_DIR, dirname(file), path)) : undefined;
      const source = target ? readFile(target) : undefined;
      const child = source ? read(source) : undefined;
      if (!target || !child) {
        found.push(`${file}:${element.loc.start.line}: <${element.tag}> takes the window's refusal and this guard cannot read it`);
        continue;
      }
      const prop = camelize(p.arg.content);
      if (seen.has(`${target}#${prop}`)) continue;
      seen.add(`${target}#${prop}`);
      found.push(...unnamedFields(target, { refusal: prop, nodes: child.nodes, voiced: child.voiced }, child.imports, readFile, seen));
    }
  });
  const { heard, mute } = controlNames(reach.nodes, reach.voiced ?? new Set());
  for (const notice of paintedApart(reach)) {
    if (heard.has(notice.key)) continue;
    const group = mute.get(notice.key);
    const why = group ? `its <${group} name="${notice.key}"> says no change: hand its ref to useGroupChange` : `no control carries name="${notice.key}"`;
    found.push(`${file}:${notice.line}: <${notice.tag}> paints ${notice.shown} apart and ${why}`);
  }
  return found;
}

/** Where the scripts read raw the fields of the refusal a window hands FormModal: of what its `:error` names, or of a
 *  command's own `error`, as `<file>:<line>: …`. */
function rawReads(file: string, error: string, scripts: readonly Script[]): string[] {
  const names = [...new Set(error.match(/[A-Za-z_$][\w$]*/g) ?? [])].filter((name) => !['null', 'undefined', 'true', 'false'].includes(name));
  const raw = new RegExp(`(?<![\\w$.])(?:${[...names, '[\\w$]+\\.error'].join('|')})(?:\\.value)?\\??\\.fields\\b`, 'g');
  return scripts.flatMap(({ content, line }) =>
    content.split('\n').flatMap((text, at) =>
      [...text.matchAll(raw)].map(
        ([read]) => `${file}:${line + at}: reads ${read} raw: FormModal never takes away what is painted from it, paint fieldErrors of its slot`,
      ),
    ),
  );
}

/** Every field without its name in the windows of the file at `path`, and every read of their refusal raw. */
function scan(path: string, readFile: Reader): string[] {
  const source = readFile(path);
  const template = source ? read(source) : undefined;
  if (!template) return [];
  return [
    ...windows(template.nodes).flatMap((reach) => unnamedFields(path, { ...reach, voiced: template.voiced }, template.imports, readFile)),
    ...handedRefusals(template.nodes).flatMap((error) => rawReads(path, error, template.scripts)),
  ];
}

// ── The hub's sources ───────────────────────────────────────────────────────────────────────────────────────────────

/** The `.vue` files of base's frontend and of every app's, relative to the hub, read once while Vitest collects this
 *  file (as external-links.test.ts does: reading them inside a test runs past Vitest's 5 s on a loaded machine). */
const SOURCES: ReadonlyMap<string, string> = new Map(
  ['base', ...readdirSync(join(HUB_DIR, 'apps'), { withFileTypes: true }).filter((app) => app.isDirectory()).map((app) => join('apps', app.name))]
    .map((root) => join(root, 'frontend'))
    .filter((frontend) => existsSync(join(HUB_DIR, frontend)))
    .flatMap((frontend) => readdirSync(join(HUB_DIR, frontend), { recursive: true, encoding: 'utf8' }).map((file) => join(frontend, file)))
    .filter((file) => file.endsWith('.vue'))
    .sort()
    .map((file) => [file, readFileSync(join(HUB_DIR, file), 'utf8')]),
);

/** Every field without its name in the hub's windows, once (a component two windows hand their refusal to is one
 *  file), as `<file>:<line>: …`. */
function everyUnnamedInTheHub(): string[] {
  return [...new Set([...SOURCES.keys()].flatMap((file) => scan(file, (path) => SOURCES.get(path))))];
}

const fileOf = (field: string): string => field.slice(0, field.indexOf(':'));
const isRawRead = (finding: string): boolean => / raw: /.test(finding);

/** The `<file>#<key>` of a refusal painted apart without a control of its name, or nothing for any other finding. */
function apartKeyOf(field: string): string | undefined {
  const key = / apart and no control carries name="(\w+)"$/.exec(field)?.[1];
  return key === undefined ? undefined : `${fileOf(field)}#${key}`;
}

const TAKEN_AWAY = new Set(Object.entries(TAKEN_AWAY_BY_THE_WINDOW).flatMap(([file, keys]) => keys.map((key) => `${file}#${key}`)));

/** Every field and refusal painted apart without its name in the hub's windows, but those a window takes away itself. */
function unnamedInTheHub(): string[] {
  return everyUnnamedInTheHub().filter((field) => !isRawRead(field) && !TAKEN_AWAY.has(apartKeyOf(field) ?? ''));
}

/** How many of `findings` each file has. */
function byFile(findings: readonly string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const finding of findings) counts[fileOf(finding)] = (counts[fileOf(finding)] ?? 0) + 1;
  return counts;
}

/** How many fields each file leaves without their name. */
const unnamedByFile = (): Record<string, number> => byFile(unnamedInTheHub());

/** Every raw read of a window's refusal in the hub. */
const rawReadsInTheHub = (): string[] => everyUnnamedInTheHub().filter(isRawRead);

/** What `found` (fields unnamed by file, `unnamedByFile()`) says against `list` (`STILL_UNNAMED`): `over`, the files with
 *  more unnamed fields than the list allows (a new field without its name); `stale`, the entries the tree no longer
 *  matches exactly (a file that named some fields keeps its old number, or left the list). */
function offTheList(found: Record<string, number>, list: Record<string, number>): { over: string[]; stale: string[] } {
  const over = Object.entries(found)
    .filter(([file, count]) => count > (list[file] ?? 0))
    .map(([file]) => file);
  const stale = Object.entries(list)
    .filter(([file, count]) => (found[file] ?? 0) !== count)
    .map(([file, count]) => `${file}: ${found[file] ?? 0} unnamed, the list says ${count}`);
  return { over, stale };
}

// ── Positive and negative controls ──────────────────────────────────────────────────────────────────────────────────

/** A window in a test: `fields` inside FormModal's default slot. */
const windowWith = (fields: string, script = '', slot = '#default="{ fieldErrors }"'): string =>
  `<script setup lang="ts">\n${script}\n</script>\n<template>\n  <FormModal v-model:open="open" title="T">\n    <template ${slot}>\n${fields}\n    </template>\n  </FormModal>\n</template>\n`;

const scanOf = (files: Record<string, string>, path = 'apps/x/frontend/components/XFormModal.vue'): string[] =>
  scan(path, (file) => files[file]);

describe('guardrail: every field of a FormModal window that paints its refusal carries its name (hub#888)', () => {
  it('sees a field that paints fieldErrors.<k> without name="<k>", or with another name', () => {
    const fields = [
      '<ion-input data-testid="year" :error-text="fieldErrors.year" />',
      '<ion-input name="nextNumber" :error-text="fieldErrors.next_number" />',
      '<ion-select :errorText="fieldErrors?.invoice_type" />',
      '<ion-textarea v-bind:error-text="fieldErrors.notes" :name="`notes${n}`" />',
    ].join('\n');
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(fields) })).toEqual([
      'apps/x/frontend/components/XFormModal.vue:7: <ion-input> paints fieldErrors.year without name="year"',
      'apps/x/frontend/components/XFormModal.vue:8: <ion-input> paints fieldErrors.next_number without name="next_number"',
      'apps/x/frontend/components/XFormModal.vue:9: <ion-select> paints fieldErrors?.invoice_type without name="invoice_type"',
      'apps/x/frontend/components/XFormModal.vue:10: <ion-textarea> paints fieldErrors.notes without name="notes"',
    ]);
  });

  it('lets through name="<k>", a literal :name, :name="<expr>" for fieldErrors[<expr>] and any name for another way', () => {
    const fields = [
      '<ion-input name="year" :error-text="fieldErrors.year" />',
      '<ion-input :name="\'next_number\'" :error-text="fieldErrors.next_number" />',
      '<ion-input v-for="field in FIELDS" :key="field" :name="field" :error-text="fieldErrors[field]" />',
      '<ion-input v-for="(line, i) in lines" :key="i" :name="`lines.${i}.price`" :error-text="errorOf(fieldErrors, i, \'price\')" />',
      '<ion-input :error-text="message" />',
      '<ion-toggle :checked="on" />',
    ].join('\n');
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(fields) })).toEqual([]);
  });

  it('sees fieldErrors[<expr>] without its :name and another way of painting it without any name', () => {
    const fields = [
      '<ion-input v-for="field in FIELDS" :key="field" :name="other" :error-text="fieldErrors[field]" />',
      '<ion-input v-for="(line, i) in lines" :key="i" :error-text="errorOf(fieldErrors, i, \'price\')" />',
      '<Combo :error-text="fieldErrors[a] || fieldErrors[`${a}_id`]" />',
    ].join('\n');
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(fields) })).toEqual([
      'apps/x/frontend/components/XFormModal.vue:7: <ion-input> paints fieldErrors[field] without :name="field"',
      "apps/x/frontend/components/XFormModal.vue:8: <ion-input> paints errorOf(fieldErrors, i, 'price') without a name",
      'apps/x/frontend/components/XFormModal.vue:9: <Combo> paints fieldErrors[a] || fieldErrors[`${a}_id`] without a name',
    ]);
  });

  it('sees a refusal the window paints apart, under a field or a group, with no control named after it (hub#1448)', () => {
    const fields = [
      '<ion-toggle :checked="on" @ion-change="on = $event.detail.checked" />',
      '<p v-if="fieldErrors.is_default" data-testid="x-is_default-error">{{ fieldErrors.is_default }}</p>',
      '<div name="customer">',
      '  <small v-if="fieldErrors.customer">{{ fieldErrors.customer }}</small>',
      '</div>',
      '<InlineFeedback v-if="fieldErrors?.days" tone="danger">{{ fieldErrors?.days }}</InlineFeedback>',
      '<span>{{ fieldErrors.buttons }}</span>',
    ].join('\n');
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(fields) })).toEqual([
      'apps/x/frontend/components/XFormModal.vue:8: <p> paints fieldErrors.is_default apart and no control carries name="is_default"',
      'apps/x/frontend/components/XFormModal.vue:10: <small> paints fieldErrors.customer apart and no control carries name="customer"',
      'apps/x/frontend/components/XFormModal.vue:12: <InlineFeedback> paints fieldErrors?.days apart and no control carries name="days"',
      'apps/x/frontend/components/XFormModal.vue:13: <span> paints fieldErrors.buttons apart and no control carries name="buttons"',
    ]);
  });

  it('lets through a refusal painted apart when a field, a group of fields or a component carries its name', () => {
    const fields = [
      '<ion-toggle name="is_default" :checked="on" />',
      '<p v-if="fieldErrors.is_default">{{ fieldErrors.is_default }}</p>',
      '<fieldset ref="tiersGroup" name="tiers">',
      '  <ion-input v-for="(tier, i) in tiers" :key="i" :name="`tiers.${i}.percent`" :error-text="fieldErrors[`tiers.${i}.percent`]" />',
      '  <p v-if="fieldErrors.tiers">{{ fieldErrors.tiers }}</p>',
      '</fieldset>',
      '<ion-checkbox v-for="day in week" :key="day" :name="\'days\'" />',
      '<InlineFeedback v-if="fieldErrors.days">{{ fieldErrors.days }}</InlineFeedback>',
      '<CustomerSearch v-model="customer" name="customer" />',
      '<small v-if="fieldErrors.customer">{{ fieldErrors.customer }}</small>',
    ].join('\n');
    const voiced = "const tiersChanged = useGroupChange('tiersGroup');";
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(fields, voiced) })).toEqual([]);
  });

  it('counts a group’s fieldset only when the window hands its ref to useGroupChange: on its own it says no change', () => {
    const group = (attributes: string): string =>
      [`<fieldset${attributes} name="tiers">`, '  <p v-if="fieldErrors.tiers">{{ fieldErrors.tiers }}</p>', '</fieldset>'].join('\n');
    const voiced = "const tiersChanged = useGroupChange('tiersGroup');";
    const mute = [
      'apps/x/frontend/components/XFormModal.vue:8: <p> paints fieldErrors.tiers apart and its <fieldset name="tiers"> says no change: hand its ref to useGroupChange',
    ];
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(group('')) })).toEqual(mute);
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(group(' ref="tiersGroup"')) })).toEqual(mute);
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(group(' ref="weekGroup"'), voiced) })).toEqual(mute);
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': windowWith(group(' ref="tiersGroup"'), voiced) })).toEqual([]);
  });

  it('sees a window that takes fieldErrors yet reads the refusal it hands FormModal raw in its script (hub#1460)', () => {
    const script = [
      'const error = computed(() => (schedule ? update.error.value : creation.error.value));',
      'const errorsByDay = computed(() => dayErrors(error.value?.fields ?? {}, sent.value));',
      "const nameError = computed(() => creation.error.value?.fields?.name ?? '');",
      'const fields = computed(() => action.value?.fields ?? []);',
    ].join('\n');
    const fields = '<p v-if="errorsByDay[day]">{{ errorsByDay[day] }}</p>';
    const source = windowWith(fields, script).replace('<FormModal ', '<FormModal :error="error" ');
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': source })).toEqual([
      'apps/x/frontend/components/XFormModal.vue:3: reads error.value?.fields raw: FormModal never takes away what is painted from it, paint fieldErrors of its slot',
      'apps/x/frontend/components/XFormModal.vue:4: reads creation.error.value?.fields raw: FormModal never takes away what is painted from it, paint fieldErrors of its slot',
    ]);
  });

  it('lets through a window that hands FormModal its refusal reshaped and paints fieldErrors of its slot, and another object’s refusal', () => {
    const script = ['const refusal = computed(() => refusalByDay(error.value));', 'const steps = computed(() => wizard.refusal.fields);'].join('\n');
    const fields = '<p v-if="fieldErrors[`days.${i}`]">{{ fieldErrors[`days.${i}`] }}</p>';
    const source = windowWith(fields, script).replace('<FormModal ', '<FormModal :error="refusal" ');
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': source })).toEqual([]);
  });

  it('sees a window that does not take fieldErrors and paints its fields from the refusal read raw (hub#1470)', () => {
    const script = [
      "const nameError = computed(() => (missing.value ? t('required') : (error.value?.fields?.name ?? null)));",
      'const fieldError = (field: string) => command.error.value?.fields?.[field] ?? null;',
    ].join('\n');
    const bare = `<script setup lang="ts">\n${script}\n</script>\n<template>\n  <FormModal :error="error" title="T">\n    <ion-input :error-text="nameError" />\n  </FormModal>\n</template>\n`;
    expect(scanOf({ 'apps/x/frontend/components/XModal.vue': bare }, 'apps/x/frontend/components/XModal.vue')).toEqual([
      'apps/x/frontend/components/XModal.vue:2: reads error.value?.fields raw: FormModal never takes away what is painted from it, paint fieldErrors of its slot',
      'apps/x/frontend/components/XModal.vue:3: reads command.error.value?.fields raw: FormModal never takes away what is painted from it, paint fieldErrors of its slot',
    ]);
  });

  it('lets through a window that does not take fieldErrors and reads nothing of its refusal raw', () => {
    const script = "const message = computed(() => (missing.value ? t('required') : undefined));";
    const bare = `<script setup lang="ts">\n${script}\n</script>\n<template>\n  <FormModal :error="error" title="T">\n    <ion-input :error-text="message" />\n  </FormModal>\n</template>\n`;
    expect(scanOf({ 'apps/x/frontend/components/XModal.vue': bare }, 'apps/x/frontend/components/XModal.vue')).toEqual([]);
  });

  it('sees a refusal painted apart in the component the window hands it to, under the prop’s name', () => {
    const files = {
      'apps/x/frontend/components/XFormModal.vue': windowWith('<WeekEditor v-model="week" :errors="fieldErrors" />', "import WeekEditor from './WeekEditor.vue';"),
      'apps/x/frontend/components/WeekEditor.vue': '<template>\n  <div>\n    <p v-if="errors.days">{{ errors.days }}</p>\n  </div>\n</template>\n',
    };
    expect(scanOf(files)).toEqual(['apps/x/frontend/components/WeekEditor.vue:3: <p> paints errors.days apart and no control carries name="days"']);
  });

  it('reads the refusal under the name the slot gives it, and on a FormModal that takes the slot itself', () => {
    const renamed = windowWith('<ion-input :error-text="errors.code" />', '', '#default="{ fieldErrors: errors }"');
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': renamed })).toEqual([
      'apps/x/frontend/components/XFormModal.vue:7: <ion-input> paints errors.code without name="code"',
    ]);
    const own = '<template>\n  <FormModal v-slot="{ fieldErrors }" title="T">\n    <ion-input :error-text="fieldErrors.code" />\n  </FormModal>\n</template>\n';
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': own })).toEqual([
      'apps/x/frontend/components/XFormModal.vue:3: <ion-input> paints fieldErrors.code without name="code"',
    ]);
  });

  it('leaves alone a page that is no FormModal window, and a window that does not take fieldErrors', () => {
    const page = '<template>\n  <ion-input :error-text="fieldErrors.code" />\n</template>\n';
    expect(scanOf({ 'apps/x/frontend/pages/XPage.vue': page }, 'apps/x/frontend/pages/XPage.vue')).toEqual([]);
    const bare = '<template>\n  <FormModal title="T">\n    <ion-input :error-text="error" />\n  </FormModal>\n</template>\n';
    expect(scanOf({ 'apps/x/frontend/components/XFormModal.vue': bare })).toEqual([]);
  });

  it('follows the refusal into the component the window hands it to, in its own file, once', () => {
    const files = {
      'apps/x/frontend/components/XFormModal.vue': windowWith(
        '<LinesEditor v-model="lines" :field-errors="fieldErrors" />\n<lines-editor v-model="more" :field-errors="fieldErrors" />',
        "import LinesEditor from './LinesEditor.vue';",
      ),
      'apps/x/frontend/components/LinesEditor.vue':
        '<template>\n  <div>\n    <ion-input :error-text="fieldErrors.description" />\n    <ion-input name="price" :error-text="fieldErrors.price" />\n  </div>\n</template>\n',
    };
    expect(scanOf(files)).toEqual(['apps/x/frontend/components/LinesEditor.vue:3: <ion-input> paints fieldErrors.description without name="description"']);
  });

  it('says so when the window hands its refusal to a component this guard cannot read', () => {
    const files = {
      'apps/x/frontend/components/XFormModal.vue': windowWith('<Lines :field-errors="fieldErrors" />', "import { Lines } from '@erplora/ui/components';"),
    };
    expect(scanOf(files)).toEqual(["apps/x/frontend/components/XFormModal.vue:7: <Lines> takes the window's refusal and this guard cannot read it"]);
  });

  it('tells the files over their number (new unnamed fields) and the stale numbers (fields named, list not lowered)', () => {
    const list = { 'a.vue': 2, 'b.vue': 1 };
    expect(offTheList({ 'a.vue': 2, 'b.vue': 1 }, list)).toEqual({ over: [], stale: [] });
    expect(offTheList({ 'a.vue': 3, 'c.vue': 1 }, list)).toEqual({
      over: ['a.vue', 'c.vue'],
      stale: ['a.vue: 3 unnamed, the list says 2', 'b.vue: 0 unnamed, the list says 1'],
    });
    expect(offTheList({ 'a.vue': 1, 'b.vue': 1 }, list)).toEqual({ over: [], stale: ['a.vue: 1 unnamed, the list says 2'] });
  });

  it('reads the real windows: it finds the windows of the hub and the fields they paint the refusal on', () => {
    const reaches = [...SOURCES.entries()].flatMap(([file, source]) => windows(read(source)?.nodes ?? []).map(() => file));
    expect(reaches.length).toBeGreaterThan(40);
    expect(reaches).toContain('apps/invoice/frontend/components/SeriesFormModal.vue');
  });

  it('reads the real windows: it finds the refusals they paint apart', () => {
    const apart = [...SOURCES.entries()].flatMap(([file, source]) =>
      windows(read(source)?.nodes ?? []).flatMap((reach) => paintedApart(reach).map((notice) => `${file}#${notice.key}`)),
    );
    expect(apart).toEqual(
      expect.arrayContaining([
        'apps/appointment/frontend/components/AppointmentFormModal.vue#customer',
        'apps/modifier/frontend/components/OptionFormModal.vue#is_default',
        'apps/pricing/frontend/components/RuleFormModal.vue#tiers',
        'apps/staff/frontend/components/ScheduleFormModal.vue#days',
        'apps/whatsapp_inbox/frontend/components/TemplateFormModal.vue#buttons',
      ]),
    );
  });
});

// ── The real tree ───────────────────────────────────────────────────────────────────────────────────────────────────

describe('the hub’s FormModal windows name the fields they paint the refusal on (hub#888)', () => {
  it('no file leaves more fields unnamed than the list says: a new field carries name="<k>"', () => {
    const over = new Set(offTheList(unnamedByFile(), STILL_UNNAMED).over);
    expect(unnamedInTheHub().filter((field) => over.has(fileOf(field)))).toEqual([]);
  });

  it('no window paints a refusal its script reads raw, whether it takes fieldErrors or not: what it paints from there stays (hub#1460, hub#1470)', () => {
    const over = new Set(offTheList(byFile(rawReadsInTheHub()), STILL_READ_RAW).over);
    expect(rawReadsInTheHub().filter((read) => over.has(fileOf(read)))).toEqual([]);
  });

  it('the raw reads only go down: a file that reads fewer lowers its number, a fixed one leaves', () => {
    expect(offTheList(byFile(rawReadsInTheHub()), STILL_READ_RAW).stale).toEqual([]);
  });

  it('the list only goes down: a file that names more of its fields lowers its number, a fixed one leaves', () => {
    expect(offTheList(unnamedByFile(), STILL_UNNAMED).stale).toEqual([]);
  });

  it('a window listed as taking a refusal away itself still paints it apart without a control of its name', () => {
    const apart = new Set(everyUnnamedInTheHub().map(apartKeyOf));
    expect([...TAKEN_AWAY].filter((entry) => !apart.has(entry))).toEqual([]);
  });

  it.each([
    ['STILL_UNNAMED', STILL_UNNAMED],
    ['STILL_READ_RAW', STILL_READ_RAW],
  ])('%s holds files of the hub with something left, in order', (_, list) => {
    const files = Object.keys(list);
    expect(Object.entries(list).filter(([, count]) => !(count > 0))).toEqual([]);
    expect(files.filter((file) => !SOURCES.has(file))).toEqual([]);
    expect(files).toEqual([...files].sort());
  });
});
