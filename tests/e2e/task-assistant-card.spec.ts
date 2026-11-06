// hub#677: since hub#416 the assistant's card left out every id its schema does not mark, so «delete the task clean the
// store room», «comment on it», «assign it to Ana» or «delete the project Opening» said no task, no project and nobody.
// Now each one is named as the screens name it — a task by its title, a project by its name, a person of the team by
// their full name —, read as the person, in their language, never by its id. End to end with the stack's SaaS gateway
// and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of
// this folder, «El asistente»). Cancelled, nothing changes. What this file creates is named «E2E Task …» (projects
// `e2e-…`) and goes away (task-helpers.ts `cleanUp`); the apps it turns on are turned off again.
// flow: TASK-F07 TASK-F10 TASK-F11 TASK-F14 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { AN_ID, cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, untilStill } from './helpers';
import { cleanUp, named, post, TAG } from './task-helpers';

/** A business is born with every app off; Tasks requires Staff. */
const NEEDED = ['staff', 'task'];

/** What the screens call each record, by the language of the card. */
const WORDS = {
  es: { task: 'Tarea', project: 'Proyecto', assignee: 'Asignada a' },
  en: { task: 'Task', project: 'Project', assignee: 'Assigned to' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

cardSpec(NEEDED, cleanUp);

/** A project, a task in it and a person of the team, through the apps' own APIs. */
async function aTeam(context: BrowserContext) {
  const tag = Date.now().toString(36);
  const project = await post<{ id: string; name: string }>(context, '/task/projects', {
    code: `e2e-${tag}`,
    name: named('Apertura'),
  });
  const task = await post<{ id: string; title: string }>(context, '/task/tasks', {
    title: named('Limpiar el almacén'),
    project_id: project.id,
  });
  const ana = await post<{ id: string; full_name: string }>(context, '/staff/members', {
    first_name: `${TAG} Ana`,
    last_name: tag,
  });
  return { project, task, ana };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`task-assistant-card — in ${language}, a write of Tasks says which task, project or person, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const { project, task, ana } = await aTeam(context);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra la tarea limpiar el almacén», a dangerous write: the task by its title, titled as its list calls one, in
    // every size.
    const deleted = await datumOf(page, 'task__task__delete', { id: task.id });
    expect([deleted.label, deleted.value]).toEqual([words.task, task.title]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.task}: ${task.title}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-677-task-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Comenta en la tarea: hecho a medias», the case of the issue: a write that is not dangerous is said in one line;
    // the task by its title, beside the comment.
    const commented = await datumOf(page, 'task__comment__add', { task_id: task.id, text: `${TAG} hecho a medias` }, 'task_id');
    expect([commented.label, commented.value]).toEqual([words.task, task.title]);
    await expect(card(page)).toContainText(task.title);
    await expect(card(page)).toContainText(`${TAG} hecho a medias`);
    await cancel(page);

    // «Asígnasela a Ana»: the person by their full name, as Staff names them.
    const assigned = await datumOf(page, 'task__task__assign', { id: task.id, member_id: ana.id }, 'member_id');
    expect([assigned.label, assigned.value]).toEqual([words.assignee, ana.full_name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(ana.full_name);
      await expect(card(page)).toContainText(task.title);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-677-assign-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Borra el proyecto Apertura»: the project by its name, titled as its list calls one.
    const removed = await datumOf(page, 'task__project__delete', { id: project.id });
    expect([removed.label, removed.value]).toEqual([words.project, project.name]);
    await expect(card(page)).toContainText(`${words.project}: ${project.name}`);
    await expect(card(page)).not.toContainText(GENERIC[language]);
    await cancel(page);

    // Cancelled, nothing changed: the task still there, in its project, unassigned and without comments; the project
    // still there.
    const tasks = await api<{ rows: { id: string; project_id: string; assigned_to_id: string | null; comment_count: number }[] }>(
      context, A, 'GET', `/task/tasks?search=${encodeURIComponent(task.title)}`,
    );
    expect(tasks.status, JSON.stringify(tasks.data)).toBe(200);
    expect(tasks.data.rows.map((row) => [row.id, row.project_id, row.assigned_to_id, row.comment_count])).toEqual([
      [task.id, project.id, null, 0],
    ]);
    const projects = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/task/projects?name=${encodeURIComponent(project.name)}`);
    expect(projects.status, JSON.stringify(projects.data)).toBe(200);
    expect(projects.data.rows.map((row) => row.id)).toEqual([project.id]);
    await context.close();
  });
}
