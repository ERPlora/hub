// The sections of Tasks (WORKBOOK «Pantallas»; the old manifest's `navigation`): Tasks and Projects, as
// the footer tabbar of every task page. Each tab follows its route and wears a registered icon, the
// same as the menu's.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { TASK_TABS, taskTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return taskTabs((key) => i18n.global.t(key));
}

describe('the task tabbar', () => {
  it('is Tasks and Projects, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['tasks', 'Tasks', '/task/tasks'],
      ['projects', 'Projects', '/task/projects'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Tareas', 'Proyectos']);
  });

  it('wears the old module\'s folder on Projects, now that the shell has it', () => {
    expect(TASK_TABS.find((tab) => tab.id === 'projects')?.icon).toBe('ion:folder-outline');
  });

  it('gives every tab a registered icon', () => {
    for (const tab of TASK_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*"([a-z_]+)",\s*_\("[^"]+"\),\s*"([^"]+)",\s*"([^"]+)",?\s*\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(TASK_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
