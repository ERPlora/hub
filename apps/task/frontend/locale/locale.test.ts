// The task app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (the old module's `locales/*.json`) are kept.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from './en.json';
import es from './es.json';

type Catalogue = { [key: string]: string | Catalogue };

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..');

function flatten(catalogue: Catalogue, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

function placeholders(message: string): string[] {
  return [...new Set([...message.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort();
}

/** The app's sources that may name a key: pages, components, composables and helpers (no tests). */
function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.(vue|ts)$/.test(entry.name) && !/\.(test|d)\.ts$/.test(entry.name) ? [path] : [];
  });
}

const EN = flatten(en as Catalogue);
const ES = flatten(es as Catalogue);

describe('task catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['task']);
    expect(Object.keys(es)).toEqual(['task']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
  });

  it('keep the same placeholders and plural forms in both languages', () => {
    for (const [key, message] of EN) {
      const spanish = ES.get(key) ?? '';
      expect(placeholders(spanish), key).toEqual(placeholders(message));
      expect(spanish.split('|').length, key).toBe(message.split('|').length);
    }
  });

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'(task\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(task\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status and priority the server knows', () => {
    for (const status of ['todo', 'in_progress', 'blocked', 'done', 'cancelled']) expect(EN.has(`task.status.${status}`), status).toBe(true);
    for (const priority of ['low', 'medium', 'high', 'urgent']) expect(EN.has(`task.priority.${priority}`), priority).toBe(true);
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states, buttons', () => {
    const words: Array<[string, string, string]> = [
      ['task.tabs.tasks', 'Tasks', 'Tareas'],
      ['task.tabs.projects', 'Projects', 'Proyectos'],
      ['task.views.all', 'All', 'Todas'],
      ['task.views.mine', 'My tasks', 'Mis tareas'],
      ['task.columns.number', 'No.', 'Nº'],
      ['task.columns.due', 'Due', 'Vence'],
      ['task.status.todo', 'To Do', 'Por hacer'],
      ['task.status.in_progress', 'In Progress', 'En curso'],
      ['task.priority.urgent', 'Urgent', 'Urgente'],
      ['task.due.overdue', 'Overdue', 'Vencida'],
      ['task.due.today', 'Due today', 'Vence hoy'],
      ['task.tasks.search', 'Search no. or title…', 'Buscar nº o título…'],
      ['task.tasks.empty', 'No tasks.', 'Sin tareas.'],
      ['task.tasks.emptyMine', 'No open tasks assigned to you.', 'Sin tareas abiertas asignadas a ti.'],
      ['task.tasks.started', 'Task started', 'Tarea iniciada'],
      ['task.tasks.completed', 'Task completed', 'Tarea completada'],
      ['task.actions.detail', 'Detail', 'Detalle'],
      ['task.actions.start', 'Start', 'Iniciar'],
      ['task.actions.assignToMe', 'Assign to me', 'Asignármela'],
      ['task.actions.unassign', 'Unassign', 'Desasignar'],
      ['task.actions.addSubtask', 'Add subtask', 'Añadir subtarea'],
      ['task.sheet.subtasks', 'Subtasks ({count})', 'Subtareas ({count})'],
      ['task.sheet.comments', 'Comments ({count})', 'Comentarios ({count})'],
      ['task.sheet.unassigned', 'Unassigned', 'Sin asignar'],
      ['task.sheet.anonymous', 'anonymous', 'anónimo'],
      ['task.sheet.newSubtask', 'New subtask…', 'Nueva subtarea…'],
      ['task.sheet.addComment', 'Add comment…', 'Añadir comentario…'],
      ['task.projects.search', 'Search code or name…', 'Buscar código o nombre…'],
      ['task.projects.empty', 'No projects.', 'Sin proyectos.'],
      ['task.projects.form.codePlaceholder', 'Code (q3-audit)', 'Código (q3-audit)'],
      ['task.projects.form.colorPlaceholder', 'Color (optional)', 'Color (opcional)'],
      ['task.projects.sheet.tasks', 'Tasks in this project ({count})', 'Tareas de este proyecto ({count})'],
      ['task.projects.sheet.more', 'Showing {shown} of {total}. Find the rest in Tasks.', 'Se muestran {shown} de {total}. El resto, en Tareas.'],
      ['task.projects.sheet.empty', 'No tasks in this project yet.', 'Este proyecto aún no tiene tareas.'],
      ['task.loading', 'Loading…', 'Cargando…'],
      ['task.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['task.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['task.noPermission', 'You do not have permission', 'No tienes permiso'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
