// The task app's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a component or
// a helper uses exists, and the screens' established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('task', en, es);
const { EN } = CATALOGUES;

describe('task catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every status and priority the server knows', () => {
    for (const status of ['todo', 'in_progress', 'blocked', 'done', 'cancelled']) expect(EN.has(`task.status.${status}`), status).toBe(true);
    for (const priority of ['low', 'medium', 'high', 'urgent']) expect(EN.has(`task.priority.${priority}`), priority).toBe(true);
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states, buttons', () => {
    expectWords(CATALOGUES, [
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
    ]);
  });
});
