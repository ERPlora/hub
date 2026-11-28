// The business a spec runs on, emptied for it and put back after: what a template brings, the plan in its photo,
// and who is signed in on it.
import { spawnSync } from 'node:child_process';

import { type BrowserContext, expect } from '@playwright/test';

import { A, api, HUB_DIR, psql } from './helpers';

/** Every row a template brings, through the server's own list of what travels (`base.blueprint.datasets`): each
 * dataset of an app that is on, last one loaded first (tables before their zones, a modifier group before the
 * product it applies to), each row through its app's own delete or archive. Personal data stays: a template never
 * brings it. Never a list of our own: it falls behind as soon as another app's data starts to travel. */
const REMOVE_TEMPLATE_DATA = [
  'from live.context import OperationContext, Scope',
  'from base.apps_on import active_apps',
  'from base.blueprint.datasets import every_dataset',
  'ctx = OperationContext(scope=Scope("host", SLUG), actor="system", permissions=frozenset({"*"}), language="en")',
  'on = active_apps(ctx.scope)',
  'for dataset in reversed(every_dataset()):',
  '    if dataset.removable and not dataset.personal and dataset.app in on:',
  '        for pk in dataset.ids(ctx):',
  '            dataset.remove(ctx, pk)',
].join('\n');

interface Datasets {
  apps: { datasets: { key: string; rows: number; personal: boolean }[] }[];
}

/**
 * Takes away every row a template brings from the business at `origin`, until the server says it is empty; when it
 * does not, the error names the datasets that kept rows.
 */
export async function emptyOfTemplateData(context: BrowserContext, origin: string): Promise<void> {
  const slug = new URL(origin).hostname.split('.')[0];
  const code = REMOVE_TEMPLATE_DATA.replace('SLUG', JSON.stringify(slug));
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', '--hub', slug, '-c', code], {
    cwd: HUB_DIR,
    env: process.env,
    encoding: 'utf8',
  });
  expect(out.status, `emptying ${slug} of what a template brings: ${out.stderr}`).toBe(0);
  const catalogue = await api<{ empty: boolean }>(context, origin, 'GET', '/settings/data/blueprints');
  expect(catalogue.status, '/settings/data/blueprints').toBe(200);
  if (catalogue.data.empty) return;
  const listed = await api<Datasets>(context, origin, 'GET', '/settings/data/datasets');
  const kept = listed.data.apps
    .flatMap((app) => app.datasets)
    .filter((dataset) => dataset.rows > 0 && !dataset.personal)
    .map((dataset) => `${dataset.key}: ${dataset.rows}`);
  throw new Error(`the business could not be emptied of what a template brings; rows kept: ${kept.join(', ')}`);
}

/**
 * The username of whoever is signed in on `context`. Not by email: a hub database kept from a stack whose SaaS was
 * created again holds an older account with the same email (a new SaaS, new users), and the email names both.
 */
export async function usernameOf(context: BrowserContext): Promise<string> {
  const me = await api<{ user: { id: string } | null }>(context, A, 'GET', '/me');
  expect(me.status, 'GET /api/me').toBe(200);
  const id = me.data.user?.id ?? '';
  expect(id, 'the person signed in').not.toBe('');
  // `/api/me` names the person of the business's database (base.HubUser), whose username is the session's.
  return psql(`SELECT username FROM base_hubuser WHERE id = '${id}'`);
}

/** Takes the plan out of `a`'s photo while a spec runs, keeping the photo in its scratch table `backup` (next to the
 * registry) for `restorePhotoFrom`: for a spec that signs in from more than one browser. With a plan in the photo
 * (erplora.com's Free covers one device, as its seed or a run of the WhatsApp specs can leave it), every entry from
 * another browser ends the sessions of the others on `a`, and the next request of the first gets a 401. */
export function dropPlanFromPhoto(backup: string): void {
  psql(`drop table if exists ${backup}; create table ${backup} as select id, state from base_hub where slug = 'a'`);
  psql("update base_hub set state = state - 'plan' where slug = 'a'");
}

/** `a`'s photo as `dropPlanFromPhoto` found it, and its scratch table `backup` dropped; nothing when it kept none. */
export function restorePhotoFrom(backup: string): void {
  if (psql(`select to_regclass('${backup}') is not null`) !== 't') return;
  psql(`update base_hub h set state = b.state from ${backup} b where b.id = h.id; drop table ${backup}`);
}
