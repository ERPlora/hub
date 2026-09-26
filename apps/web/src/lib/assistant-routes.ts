// How the assistant panel NAMES a screen of the shell (hub#2204).
//
// The answer mentions screens by path (`/m/cash_register/settings`, `/settings#permissions`, …) and the
// drawer turns them into «Go to …» buttons and links. They read «Cash_register › settings»: the
// module id with a capital letter and the raw tab id — identifiers the owner meets nowhere else.
// The sidebar, the launcher and the module tab bar name the app and the screen from
// `/api/navigation`, translated by the runtime (ADR-0055); the drawer uses those same names.
import type { ModuleNavItem } from './nav';

export interface RouteLabelSource {
  /** The installed modules as the sidebar lists them (`moduleNav`), with their tabs. */
  modules: readonly ModuleNavItem[];
  t: (key: string) => string;
}

/** The shell's own screens, by the key of their menu entry. */
const SHELL_SCREENS: Record<string, string> = {
  dashboard: 'nav.home',
  employees: 'nav.employees',
  settings: 'nav.settings',
  apps: 'nav.apps',
  system: 'nav.system',
  billing: 'nav.billing',
};

/**
 * The least bad name for an identifier nobody translated: its words, first letter capitalised.
 * `cash_register` → `Cash register`. Never the underscore.
 */
function asWords(id: string): string {
  const words = id.replace(/[_-]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** «App › Screen» for `/m/<module>[/<tab>]`, the menu name for a shell screen. */
export function routeLabel(url: string, { modules, t }: RouteLabelSource): string {
  const m = /^\/m\/([\w-]+)(?:\/([\w-]+))?/.exec(url);
  if (m) {
    const [, moduleId, tabId] = m;
    const mod = modules.find((entry) => entry.path === `/m/${moduleId}`);
    const app = mod?.label || asWords(moduleId);
    if (!tabId) return app;
    const tab = mod?.tabs?.find((entry) => entry.id === tabId)?.label;
    // `settings` is the tab the SHELL adds from the module's settings block (ModuleView), so it is
    // named like there unless the module declares a tab of its own with that id.
    const screen = tab || (tabId === 'settings' ? t('moduleSettings.tab') : asWords(tabId));
    return `${app} › ${screen}`;
  }
  const screen = /^\/([\w-]+)/.exec(url)?.[1] ?? '';
  const key = SHELL_SCREENS[screen];
  return key ? t(key) : asWords(screen);
}
