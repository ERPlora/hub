// The public pages are Bootstrap 5.3 (Ioan, 2026-10-22): every class in the website's Django templates
// (`apps/website/templates/website/**`) and in the catalog the bundle rebuilds is one of Bootstrap's own, read from
// the installed `bootstrap.css`, or a `ws-*` hook; no class is computed (`{{ … }}`), so this scan sees them all. Each
// hook is defined in `site.css`, the one stylesheet of our own, and the stylesheet defines no hook nobody uses.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { catalogNodes } from './catalog';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB = join(HERE, '..', '..', '..', '..');
const TEMPLATES = join(HERE, '..', '..', 'templates', 'website');
const SITE_CSS = readFileSync(join(HERE, 'site.css'), 'utf8');

/** The class names Bootstrap 5.3 defines: every `.name` in a selector of its stylesheet. */
function bootstrapClasses(): Set<string> {
  const css = readFileSync(join(HUB, 'node_modules', 'bootstrap', 'dist', 'css', 'bootstrap.css'), 'utf8').replace(
    /\/\*[\s\S]*?\*\//g,
    '',
  );
  const names = new Set<string>();
  for (const [, selector] of css.matchAll(/([^{};]+)\{/g)) {
    for (const [, name] of selector.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) names.add(name);
  }
  return names;
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : path.endsWith('.html') ? [path] : [];
  });
}

/** Each `class="…"` of a template, with its Django tags taken out (the classes on both sides of an `{% if %}`). */
function templateClasses(path: string): { attribute: string; tokens: string[] }[] {
  const source = readFileSync(path, 'utf8');
  return [...source.matchAll(/\bclass="([^"]*)"/g)].map(([, attribute]) => ({
    attribute,
    tokens: attribute.replace(/\{%[\s\S]*?%\}/g, ' ').split(/\s+/).filter(Boolean),
  }));
}

function catalogClasses(): string[] {
  const catalog = {
    source: 'service' as const,
    show_prices: true,
    groups: [{ name: 'Hair', items: [{ name: 'Cut', price: 1500, price_kind: 'fixed' as const, minutes: 30, price_label: '€15.00' }] }],
  };
  const nodes = [...catalogNodes(catalog, 'Empty'), ...catalogNodes({ ...catalog, groups: [] }, 'Empty')];
  return nodes.flatMap((node) => [node, ...node.querySelectorAll('*')].flatMap((el) => [...el.classList]));
}

const BOOTSTRAP = bootstrapClasses();
const TEMPLATE_FILES = files(TEMPLATES);
const isHook = (name: string) => /^ws-[a-z0-9-]+$/.test(name);
const hooksDefined = new Set([...SITE_CSS.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/\.(ws-[a-z0-9-]+)/g)].map(([, name]) => name));

describe('the public website’s classes', () => {
  it('reads Bootstrap 5.3’s own stylesheet', () => {
    for (const name of ['container', 'navbar-expand-md', 'row-cols-md-2', 'bg-body-tertiary', 'object-fit-cover', 'ratio-16x9']) {
      expect(BOOTSTRAP.has(name), name).toBe(true);
    }
    expect(BOOTSTRAP.has('ws-display')).toBe(false);
  });

  it('every template is scanned, the four designs and the sections they share', () => {
    const names = TEMPLATE_FILES.map((path) => relative(TEMPLATES, path)).sort();
    expect(names).toEqual(
      expect.arrayContaining([
        'base.html',
        'templates/classic.html',
        'templates/modern.html',
        'templates/minimal.html',
        'templates/bold.html',
        'sections/about.html',
        'sections/catalog.html',
        'sections/gallery.html',
        'sections/contact.html',
        'sections/location.html',
      ]),
    );
  });

  it.each(TEMPLATE_FILES.map((path) => [relative(TEMPLATES, path), path]))(
    '%s uses only Bootstrap’s classes and ws-* hooks, never a computed one',
    (_name, path) => {
      for (const { attribute, tokens } of templateClasses(path)) {
        expect(attribute, 'a class computed from a variable cannot be checked').not.toContain('{{');
        for (const token of tokens) expect(BOOTSTRAP.has(token) || isHook(token), `${token} in class="${attribute}"`).toBe(true);
      }
    },
  );

  it('the catalog the bundle rebuilds uses only Bootstrap’s classes and ws-* hooks', () => {
    for (const token of catalogClasses()) expect(BOOTSTRAP.has(token) || isHook(token), token).toBe(true);
  });

  it('every ws-* hook is defined in site.css, and site.css defines none that is not used', () => {
    const used = new Set([
      ...TEMPLATE_FILES.flatMap((path) => templateClasses(path).flatMap(({ tokens }) => tokens)),
      ...catalogClasses(),
    ].filter(isHook));
    expect(used.size).toBeGreaterThan(0);
    for (const hook of used) expect(hooksDefined.has(hook), `.${hook} is not in site.css`).toBe(true);
    for (const hook of hooksDefined) expect(used.has(hook), `.${hook} is in site.css but no template uses it`).toBe(true);
  });

  it('no hook stands in for a class Bootstrap already has', () => {
    for (const hook of hooksDefined) expect(BOOTSTRAP.has(hook.replace(/^ws-/, '')), hook).toBe(false);
  });
});
