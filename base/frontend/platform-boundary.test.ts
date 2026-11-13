// base is the platform: always installed and with no `requires`, so its frontend never imports
// a module's code (a type, a component, an operation). Such an import ties the Home to an app a hub may not have:
// «Activity» reads Sales by the operation's name (`sale.sale.list`) and keeps its own type of the row.
// The one door into `apps/` is the extension point of the hooks: `lib/app-components.ts`
// loads the component a module declares for its panel of the Home or its card of System with `import.meta.glob`, so base
// never names a module.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

/** base/frontend, the folder this guard reads; the hub's root is two levels up. */
const BASE_FRONTEND = dirname(fileURLToPath(import.meta.url));
const APPS_DIR = resolve(BASE_FRONTEND, '..', '..', 'apps');

/** The declared extension point (the panels of the Home, the cards of System): the only reach of base/frontend into apps/. */
const ALLOWED_GLOBS: readonly { file: string; pattern: string }[] = [
  { file: 'lib/app-components.ts', pattern: '../../../apps/*/frontend/components/*.vue' },
];

/** Every way a source names another file: import (also `import type` and multi-line), re-export, bare and dynamic import. */
const SPECIFIERS = [
  /\bimport\s+(?:type\s+)?[^'"`;]*?\bfrom\s*['"]([^'"]+)['"]/g,
  /\bimport\s*['"]([^'"]+)['"]/g,
  /\bexport\s+(?:type\s+)?(?:\*(?:\s+as\s+\w+)?|\{[^}]*\})\s*from\s*['"]([^'"]+)['"]/g,
  /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
];
/** `import.meta.glob(<pattern or [patterns]>)`, with or without its type argument. */
const GLOBS = /\bimport\.meta\.glob(?:<[^>]*>)?\s*\(\s*(\[[^\]]*\]|['"][^'"]+['"])/g;
const QUOTED = /['"]([^'"]+)['"]/g;

function insideApps(fromFile: string, specifier: string): boolean {
  if (!specifier.startsWith('.')) return false;
  const path = relative(APPS_DIR, resolve(dirname(fromFile), specifier));
  return path === '' || (!path.startsWith('..') && !isAbsolute(path));
}

/** The specifiers of `source` (the file at `file`, relative to base/frontend) that reach into apps/. */
function appImports(file: string, source: string): string[] {
  const absolute = join(BASE_FRONTEND, file);
  const found: string[] = [];
  for (const pattern of SPECIFIERS) {
    for (const [, specifier] of source.matchAll(pattern)) {
      if (insideApps(absolute, specifier)) found.push(`${file}: ${specifier}`);
    }
  }
  for (const [, argument] of source.matchAll(GLOBS)) {
    for (const [, specifier] of argument.matchAll(QUOTED)) {
      const allowed = ALLOWED_GLOBS.some((glob) => glob.file === file && glob.pattern === specifier);
      if (!allowed && insideApps(absolute, specifier)) found.push(`${file}: import.meta.glob ${specifier}`);
    }
  }
  return found;
}

function sources(): string[] {
  return readdirSync(BASE_FRONTEND, { recursive: true, encoding: 'utf8' })
    .filter((file) => /\.(ts|vue)$/.test(file))
    .sort();
}

describe('guardrail: base/frontend imports no module', () => {
  it('sees every way of naming a module, and lets the packages, base and the components door through', () => {
    const planted = [
      "import type { SaleRow } from '../../../apps/sale/frontend/operations';",
      "import SalePanel from '../../../apps/sale/frontend/components/SalePanel.vue';",
      'import {\n  formatTotal,\n  type Totals,\n} from "../../../apps/sale/frontend/lib/totals";',
      "import '../../../apps/sale/frontend/styles.css';",
      "export type { SaleRow } from '../../../apps/sale/frontend/operations';",
      "export * from '../../../apps/sale/frontend/lib/totals';",
      "const page = () => import('../../../apps/sale/frontend/pages/SalesPage.vue');",
      "const all = import.meta.glob('../../../apps/*/frontend/pages/*.vue');",
      "import { useLive } from '@erplora/ui/sdk';",
      "import { formatValue } from '../lib/home';",
      "const widgets = import.meta.glob<{ default: Component }>('../../../apps/*/frontend/components/*.vue');",
    ].join('\n');

    expect(appImports('lib/app-components.ts', planted)).toEqual([
      'lib/app-components.ts: ../../../apps/sale/frontend/operations',
      'lib/app-components.ts: ../../../apps/sale/frontend/components/SalePanel.vue',
      'lib/app-components.ts: ../../../apps/sale/frontend/lib/totals',
      'lib/app-components.ts: ../../../apps/sale/frontend/styles.css',
      'lib/app-components.ts: ../../../apps/sale/frontend/operations',
      'lib/app-components.ts: ../../../apps/sale/frontend/lib/totals',
      'lib/app-components.ts: ../../../apps/sale/frontend/pages/SalesPage.vue',
      'lib/app-components.ts: import.meta.glob ../../../apps/*/frontend/pages/*.vue',
    ]);
    // The components door is lib/app-components.ts's alone: the same glob anywhere else (the panel or the cards that
    // mount what it loads included) is a reach into the modules.
    for (const file of ['components/HomeActivity.vue', 'components/WidgetPanel.vue', 'components/SystemAppCards.vue']) {
      expect(appImports(file, planted)).toContain(`${file}: import.meta.glob ../../../apps/*/frontend/components/*.vue`);
    }
  });

  it('no source of base/frontend imports from apps/ (the components door aside)', () => {
    const files = sources();
    expect(files).toContain('components/HomeActivity.vue');
    expect(files.flatMap((file) => appImports(file, readFileSync(join(BASE_FRONTEND, file), 'utf8')))).toEqual([]);
  });
});
