// FieldGroup is the one group of controls without the fieldset's box. A window that groups a customer, a week or a
// package's lines without a box uses it, rather than a <fieldset> whose own class takes the border, margin and padding
// away by hand: the guard at the end finds such copies in the Hub's windows.
import { mount } from '@vue/test-utils';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';
import { parse } from 'vue/compiler-sfc';

import FieldGroup from './FieldGroup.vue';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB_DIR = join(HERE, '..', '..', '..');
const OWN_FILE = join(HERE, 'FieldGroup.vue');

const ELEMENT = 1;
const ATTRIBUTE = 6;

interface TemplateNode {
  type: number;
  tag?: string;
  props?: { type: number; name: string; value?: { content: string } }[];
  children?: TemplateNode[];
}

/** The declarations of each rule in `css`, by selector: `.a, .b { margin: 0 }` gives both `.a` and `.b` its body. */
function rules(css: string): Map<string, Record<string, string>> {
  const found = new Map<string, Record<string, string>>();
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, '');
  for (const [, selectors, body] of bare.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const declarations: Record<string, string> = {};
    for (const line of body.split(';')) {
      const [property, ...value] = line.split(':');
      if (value.length > 0) declarations[property.trim()] = value.join(':').trim();
    }
    for (const selector of selectors.split(',')) found.set(selector.trim(), { ...found.get(selector.trim()), ...declarations });
  }
  return found;
}

const BORDERLESS = /^(?:0|none)(?:\s*!important)?$/;

function takesBorderAway(declarations: Record<string, string> | undefined): boolean {
  if (!declarations) return false;
  return ['border', 'border-width', 'border-style'].some((property) => BORDERLESS.test(declarations[property] ?? ''));
}

/** The plain classes of every native `<fieldset>` in `nodes`. */
function fieldsetClasses(nodes: readonly TemplateNode[]): string[][] {
  const found: string[][] = [];
  for (const node of nodes) {
    if (node.type !== ELEMENT) continue;
    if (node.tag === 'fieldset') {
      const attribute = node.props?.find((p) => p.type === ATTRIBUTE && p.name === 'class');
      found.push((attribute?.value?.content ?? '').split(/\s+/).filter(Boolean));
    }
    found.push(...fieldsetClasses(node.children ?? []));
  }
  return found;
}

/** The native fieldsets of `source` (the file at `file`) whose own class takes their border away. */
function boxlessByHand(file: string, source: string): string[] {
  const { descriptor } = parse(source);
  const nodes = (descriptor.template?.ast as unknown as { children: TemplateNode[] } | undefined)?.children ?? [];
  const own = rules(descriptor.styles.map((style) => style.content).join('\n'));
  return fieldsetClasses(nodes)
    .filter((classes) => classes.some((name) => takesBorderAway(own.get(`.${name}`))))
    .map((classes) => `${file}: <fieldset class="${classes.join(' ')}"> takes its box away by hand: use FieldGroup`);
}

function windowSources(): string[] {
  const roots = ['base/frontend', ...readdirSync(join(HUB_DIR, 'apps')).map((app) => `apps/${app}/frontend`)];
  return roots
    .filter((root) => existsSync(join(HUB_DIR, root)))
    .flatMap((root) => readdirSync(join(HUB_DIR, root), { recursive: true, encoding: 'utf8' }).map((file) => join(HUB_DIR, root, file)))
    .filter((path) => path.endsWith('.vue') && !path.includes('node_modules') && path !== OWN_FILE)
    .sort();
}

describe('FieldGroup', () => {
  it('holds its controls in a fieldset that keeps the attributes the window gives it', () => {
    const wrapper = mount(FieldGroup, {
      attrs: { name: 'days', class: 'staff-week', 'aria-label': 'Week', 'data-testid': 'week' },
      slots: { default: '<legend>Week</legend><input name="monday">' },
    });
    const root = wrapper.element as HTMLFieldSetElement;
    expect(root.tagName).toBe('FIELDSET');
    expect([root.name, root.classList.contains('staff-week'), root.getAttribute('aria-label'), root.dataset.testid]).toEqual([
      'days',
      true,
      'Week',
      'week',
    ]);
    expect(root.firstElementChild?.outerHTML).toBe('<legend>Week</legend>');
    expect(root.elements.namedItem('monday')).not.toBeNull();
  });

  it('takes the box away — no border, margin or padding — and lets the group shrink with the window', () => {
    const root = mount(FieldGroup).element as HTMLElement;
    const { descriptor } = parse(readFileSync(OWN_FILE, 'utf8'));
    expect(descriptor.styles.map((style) => style.scoped)).toEqual([true]);
    const own = rules(descriptor.styles[0].content);
    expect([...root.classList].map((name) => own.get(`.${name}`))).toEqual([{ 'min-width': '0', margin: '0', padding: '0', border: '0' }]);
  });
});

describe('a group without a box is a FieldGroup', () => {
  it('no window of the Hub takes a fieldset’s box away by hand', () => {
    const found = windowSources().flatMap((path) => boxlessByHand(relative(HUB_DIR, path), readFileSync(path, 'utf8')));
    expect(found).toEqual([]);
  });

  it('sees a fieldset whose own class takes its border away, and lets a box of its own or a FieldGroup through', () => {
    const window = (template: string, css: string): string => `<template>\n${template}\n</template>\n<style scoped>\n${css}\n</style>\n`;
    const file = 'apps/x/frontend/components/XFormModal.vue';
    expect(boxlessByHand(file, window('<div><fieldset class="x-form x-week"><legend>Week</legend></fieldset></div>', '.x-week { display: grid; margin: 0; padding: 0; border: 0; }'))).toEqual([
      `${file}: <fieldset class="x-form x-week"> takes its box away by hand: use FieldGroup`,
    ]);
    expect(boxlessByHand(file, window('<fieldset class="x-week" />', '/* no box */\n.x-other,\n.x-week {\n  border: none;\n}'))).toHaveLength(1);
    expect(boxlessByHand(file, window('<fieldset class="x-week" />', '.x-week { border-width: 0; }'))).toHaveLength(1);
    expect(boxlessByHand(file, window('<fieldset class="x-tiers" />', '.x-tiers { border: 1px solid var(--ion-border-color); }'))).toEqual([]);
    expect(boxlessByHand(file, window('<fieldset class="x-tiers" />', '.x-tiers legend { border: 0; }'))).toEqual([]);
    expect(boxlessByHand(file, window('<FieldGroup class="x-week" />', '.x-week { display: grid; border: 0; }'))).toEqual([]);
  });
});
