// `pnpm gen:app-icons`: bakes the `icon` of every module's apps.py into
// frontend/generated/app-icons.json, `{"<icon>": "<svg>"}` (round 16, spec §4.6). `register_apps`
// copies each SVG into `shared.app.icon_svg`, which the SaaS paints inline after cleaning it with
// nh3, so every SVG is whole and self-contained: no CSS classes, painted in currentColor. Commit the
// result: frontend/generated/app-icons.test.ts fails when it falls out of step with the apps.py files.
//
// The sources are the shell's own icon packages, resolved from @erplora/ui (packages/ui):
// `ionicons/icons` for `ion:`, `@iconify-json/<set>` for the Iconify sets. Everything is read from
// disk: no network, ever (PLAN §16.4).
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

export const APP_ICONS_PATH = join(HUB_DIR, 'frontend', 'generated', 'app-icons.json');
const DEFAULT_SET = 'ion';
/** The Iconify sets the shell installs (packages/ui/package.json). */
const ICONIFY_SETS = ['lucide', 'mdi', 'material-symbols'];
/** A module's own `icon = "set:name"` class attribute; a menu's `Nav(icon="…")` is not one. */
const MODULE_ICON = /^[ \t]+icon\s*=\s*["']([^"']+)["']/gm;

/** Resolves packages the way @erplora/ui does: they are its dependencies, not the hub's. */
const requireFromUi = createRequire(join(HUB_DIR, 'packages', 'ui', 'package.json'));

/** The `icon` of every `apps/<id>/apps.py` under `root`, sorted and once each. */
export function moduleIcons(root = HUB_DIR) {
  const appsDir = join(root, 'apps');
  const icons = new Set();
  for (const entry of readdirSync(appsDir, { withFileTypes: true })) {
    const appsPy = join(appsDir, entry.name, 'apps.py');
    if (!entry.isDirectory() || !existsSync(appsPy)) continue;
    for (const [, icon] of readFileSync(appsPy, 'utf8').matchAll(MODULE_ICON)) icons.add(icon);
  }
  return [...icons].sort();
}

let ionicons;
const iconifySets = new Map();

function camelCase(name) {
  return name.replace(/-([a-z0-9])/g, (_, char) => char.toUpperCase());
}

/** What ion-icon's shadow CSS gives the classes of `ionicons/icons`, as presentation attributes. */
const IONICON_CLASS_ATTRIBUTES = {
  'ionicon-fill-none': ['fill', 'none'],
  'ionicon-stroke-width': ['stroke-width', '32'],
};

/**
 * An Ionicon's body without ion-icon's CSS: each class becomes its attribute (replacing one the
 * element sets itself, as the CSS rule beat it) and the whole is wrapped in the stroke colour the
 * `.ionicon` root rule gave. Inline, those classes would mean nothing.
 */
function selfContainedIonicon(key, body) {
  const inlined = body.replace(/<([a-z]+)([^>]*?) class='([^']*)'([^>]*)>/g, (_, tag, before, classes, after) => {
    let attributes = `${before}${after.replace(/\/$/, '')}`;
    for (const name of classes.split(/\s+/).filter(Boolean)) {
      const attribute = IONICON_CLASS_ATTRIBUTES[name];
      if (!attribute) throw new Error(`Icon ${key}: ionicons class ${name} has no known attribute.`);
      const [prop, value] = attribute;
      const existing = new RegExp(` ${prop}='[^']*'`);
      attributes = existing.test(attributes)
        ? attributes.replace(existing, ` ${prop}='${value}'`)
        : `${attributes} ${prop}='${value}'`;
    }
    return `<${tag}${attributes}${after.endsWith('/') ? '/' : ''}>`;
  });
  return `<g stroke='currentColor'>${inlined}</g>`;
}

function resolveIonicon(key, name) {
  ionicons ??= requireFromUi('ionicons/icons');
  const url = ionicons[camelCase(name)];
  if (typeof url !== 'string') throw new Error(`Icon ${key} does not exist in ionicons.`);
  const svg = decodeURIComponent(url.slice(url.indexOf(',') + 1));
  const viewBox = /viewBox=['"]([^'"]+)['"]/.exec(svg)?.[1];
  const body = svg.slice(svg.indexOf('>') + 1, svg.lastIndexOf('</svg>'));
  if (!viewBox || !body) throw new Error(`Icon ${key}: ionicons gave an SVG this script cannot read.`);
  return { body: selfContainedIonicon(key, body), viewBox };
}

/** An Iconify icon, or the icon an alias points to (aliases may chain). */
function iconifyEntry(data, name, depth = 0) {
  if (data.icons[name]) return data.icons[name];
  const alias = data.aliases?.[name];
  if (!alias || depth > 8) return undefined;
  const parent = iconifyEntry(data, alias.parent, depth + 1);
  return parent && { ...parent, ...alias };
}

function resolveIconify(key, set, name) {
  if (!iconifySets.has(set)) iconifySets.set(set, requireFromUi(`@iconify-json/${set}/icons.json`));
  const data = iconifySets.get(set);
  const icon = iconifyEntry(data, name);
  if (!icon?.body) throw new Error(`Icon ${key} does not exist in @iconify-json/${set}.`);
  const left = icon.left ?? data.left ?? 0;
  const top = icon.top ?? data.top ?? 0;
  const width = icon.width ?? data.width ?? 16;
  const height = icon.height ?? data.height ?? 16;
  return { body: icon.body, viewBox: `${left} ${top} ${width} ${height}` };
}

/** `{ body, viewBox }` of one `set:name` key (a bare name is an Ionicon); throws naming the key. */
function resolveIcon(key) {
  const [set, name] = key.includes(':') ? key.split(/:(.*)/s) : [DEFAULT_SET, key];
  if (set === DEFAULT_SET) return resolveIonicon(key, name);
  if (ICONIFY_SETS.includes(set)) return resolveIconify(key, set, name);
  throw new Error(`Icon ${key}: unknown set; the shell has ${[DEFAULT_SET, ...ICONIFY_SETS].join(', ')}.`);
}

/** One icon as a whole SVG element, as the SaaS's `{% icon %}` paints its own (fill currentColor). */
export function bakeIcon(key) {
  const { body, viewBox } = resolveIcon(key);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" fill="currentColor">${body}</svg>`;
}

/** The baked icons of the modules of the hub at `root`. */
export function buildAppIcons(root = HUB_DIR) {
  return Object.fromEntries(moduleIcons(root).map((key) => [key, bakeIcon(key)]));
}

/** Stable JSON: sorted keys, two-space indent, final newline. */
export function renderAppIcons(icons) {
  const sorted = Object.fromEntries(Object.keys(icons).sort().map((key) => [key, icons[key]]));
  return `${JSON.stringify(sorted, null, 2)}\n`;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const icons = buildAppIcons();
  writeFileSync(APP_ICONS_PATH, renderAppIcons(icons));
  console.log(`${APP_ICONS_PATH}: ${Object.keys(icons).length} icons`);
}
