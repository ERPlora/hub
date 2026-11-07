// @vitest-environment node
// Guardrail of the windows' fields (hub#888): FormModal (@erplora/ui) takes a mark away from the refused field a
// person corrects, and it tells that field by its `name` when the name is a key of the refusal; without one it
// falls back to the words the field shows, and two fields refused with the same words («Enter a whole number.» under
// the year and the next number of a new series) are not told apart: correcting one leaves both marked. So every field
// of a FormModal window that paints the window's refusal (`:error-text="fieldErrors.<k>"`) carries `name="<k>"`; one
// that paints `fieldErrors[<expr>]` carries `:name="<expr>"`; one that paints it some other way
// (`errorOf(fieldErrors, index, 'price')`) carries a `name` of its own. The same holds in a component the window hands
// its refusal to (`:field-errors="fieldErrors"`), followed to its file. The files still waiting are listed below with
// how many fields they leave unnamed; the number only goes down, and a fixed file leaves the list.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';
import { parse } from 'vue/compiler-sfc';

/** The root of the hub: the paths below are relative to it. */
const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

/** What is left of the fields without their name, by file: it only goes down. COMBO: a `name` on `<Combo>` would pass
 *  this guard and fix nothing: Combo (@erplora/ui) does not declare the prop and its root is a div, and FormModal reads
 *  the `name` property of the field, not the attribute. Those fields stay counted here until Combo hands its name to
 *  its ion-input. */
const STILL_UNNAMED: Record<string, number> = {
  'apps/appointment/frontend/components/AppointmentFormModal.vue': 6,
  'apps/appointment/frontend/components/SeriesFormModal.vue': 8,
  'apps/attendance/frontend/components/CorrectionModal.vue': 3,
  'apps/cart_checkout/frontend/components/CartFormModal.vue': 3,
  'apps/cart_checkout/frontend/components/FailOrderModal.vue': 1,
  'apps/combo/frontend/components/MenuFormModal.vue': 5,
  'apps/kitchen/frontend/components/StationFormModal.vue': 2,
  'apps/kitchen/frontend/components/TicketFormModal.vue': 1,
  'apps/modifier/frontend/components/GroupFormModal.vue': 5,
  'apps/modifier/frontend/components/OptionFormModal.vue': 5,
  'apps/payment/frontend/components/CancelPaymentModal.vue': 1,
  'apps/payment/frontend/components/MethodFormModal.vue': 3,
  'apps/payment/frontend/components/PaymentFormModal.vue': 7,
  'apps/pricing/frontend/components/PriceItemFormModal.vue': 3,
  'apps/pricing/frontend/components/PriceListFormModal.vue': 7,
  'apps/pricing/frontend/components/RuleFormModal.vue': 16,
  'apps/reservation/frontend/components/BlockedDateFormModal.vue': 3,
  'apps/reservation/frontend/components/ReservationFormModal.vue': 10,
  'apps/reservation/frontend/components/SlotFormModal.vue': 4,
  'apps/reservation/frontend/components/WaitlistFormModal.vue': 5,
  'apps/sale/frontend/components/backoffice/DepartmentFormModal.vue': 3,
  'apps/sale/frontend/components/backoffice/QuickNoteFormModal.vue': 2,
  'apps/service/frontend/components/CategoryFormModal.vue': 3,
  'apps/service/frontend/components/GrantAdjustModal.vue': 3,
  'apps/service/frontend/components/GrantVoidModal.vue': 1,
  'apps/service/frontend/components/PackageFormModal.vue': 8,
  'apps/service/frontend/components/ServiceFormModal.vue': 6,
  'apps/staff/frontend/components/MemberFormModal.vue': 2, // Role and Hub user: Combos (see COMBO above)
  'apps/staff/frontend/components/TimeOffFormModal.vue': 1, // Team member: a Combo
  'apps/table/frontend/components/TableFormModal.vue': 3,
  'apps/table/frontend/components/ZoneFormModal.vue': 3,
  'apps/task/frontend/components/TaskFormModal.vue': 2, // Assigned to and Project: Combos
  'apps/tax/frontend/components/AliasCreateModal.vue': 3,
  'apps/tax/frontend/components/CategoryCreateModal.vue': 3,
  'apps/tax/frontend/components/RuleCreateModal.vue': 12,
  'apps/tax/frontend/components/RuleEndModal.vue': 1,
  'apps/whatsapp_inbox/frontend/components/TemplateFormModal.vue': 5,
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
type TemplateNode = Element | { type: number; children?: unknown };

const ELEMENT = 1;
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

/** A source's components brought from a `.vue` file of the hub, by name: `{ RecipientFields: './RecipientFields.vue' }`. */
function vueImports(script: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const [, name, path] of script.matchAll(/\bimport\s+(\w+)\s+from\s*['"](\.{1,2}\/[^'"]+\.vue)['"]/g)) found[name] = path;
  return found;
}

/** A source's template tree and the components it imports, or nothing when it has no template. */
function read(source: string): { nodes: TemplateNode[]; imports: Record<string, string> } | undefined {
  const { descriptor } = parse(source);
  const ast = descriptor.template?.ast as unknown as { children: TemplateNode[] } | undefined;
  if (!ast) return undefined;
  return { nodes: ast.children, imports: vueImports(`${descriptor.script?.content ?? ''}\n${descriptor.scriptSetup?.content ?? ''}`) };
}

/** Where a window's refusal goes: the name its fields read it by (`fieldErrors`) and the nodes that read it. */
interface Reach {
  refusal: string;
  nodes: readonly TemplateNode[];
}

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
    if (element.tag !== 'FormModal' && element.tag !== 'form-modal') return;
    const own = slotOf(element);
    if (own) found.push(own);
    for (const child of element.children) {
      const slot = isElement(child) && child.tag === 'template' ? slotOf(child) : undefined;
      if (slot) found.push(slot);
    }
  });
  return found;
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
      found.push(...unnamedFields(target, { refusal: prop, nodes: child.nodes }, child.imports, readFile, seen));
    }
  });
  return found;
}

/** Every field without its name in the windows of the file at `path`. */
function scan(path: string, readFile: Reader): string[] {
  const source = readFile(path);
  const template = source ? read(source) : undefined;
  if (!template) return [];
  return windows(template.nodes).flatMap((reach) => unnamedFields(path, reach, template.imports, readFile));
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
function unnamedInTheHub(): string[] {
  return [...new Set([...SOURCES.keys()].flatMap((file) => scan(file, (path) => SOURCES.get(path))))];
}

const fileOf = (field: string): string => field.slice(0, field.indexOf(':'));

/** How many fields each file leaves without their name. */
function unnamedByFile(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const field of unnamedInTheHub()) counts[fileOf(field)] = (counts[fileOf(field)] ?? 0) + 1;
  return counts;
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

  it('reads the real windows: it finds the windows of the hub and the fields they paint the refusal on', () => {
    const reaches = [...SOURCES.entries()].flatMap(([file, source]) => windows(read(source)?.nodes ?? []).map(() => file));
    expect(reaches.length).toBeGreaterThan(40);
    expect(reaches).toContain('apps/invoice/frontend/components/SeriesFormModal.vue');
  });
});

// ── The real tree ───────────────────────────────────────────────────────────────────────────────────────────────────

describe('the hub’s FormModal windows name the fields they paint the refusal on (hub#888)', () => {
  it('no file leaves more fields unnamed than the list says: a new field carries name="<k>"', () => {
    const over = new Set(
      Object.entries(unnamedByFile())
        .filter(([file, count]) => count > (STILL_UNNAMED[file] ?? 0))
        .map(([file]) => file),
    );
    expect(unnamedInTheHub().filter((field) => over.has(fileOf(field)))).toEqual([]);
  });

  it('the list only goes down: a file that names more of its fields lowers its number, a fixed one leaves', () => {
    const found = unnamedByFile();
    const stale = Object.entries(STILL_UNNAMED)
      .filter(([file, count]) => (found[file] ?? 0) !== count)
      .map(([file, count]) => `${file}: ${found[file] ?? 0} unnamed, the list says ${count}`);
    expect(stale).toEqual([]);
  });

  it('the list holds files of the hub with fields left, in order', () => {
    const files = Object.keys(STILL_UNNAMED);
    expect(Object.entries(STILL_UNNAMED).filter(([, count]) => !(count > 0))).toEqual([]);
    expect(files.filter((file) => !SOURCES.has(file))).toEqual([]);
    expect(files).toEqual([...files].sort());
  });
});
