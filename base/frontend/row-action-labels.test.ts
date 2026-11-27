// A row action (or a list's main action) with an icon is the icon alone: its label is the button's accessible name and
// tooltip, which the DataTable already gives it. `showLabel` paints the label beside the icon too, and only an action
// whose icon cannot say it alone keeps it. This guard reads the scripts of base and of every app, and every `showLabel`
// it finds has to be one of the exceptions below; the list only shrinks, and an exception that is no longer there is
// struck off it.
import { readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { bare, findingsByApp, HUB, hubFrontends, linesWhere, scriptBlocks } from './__tests__/frontend-sources';
import { NO_CLOCK } from '../../vitest.load';

/** `<path from the hub>#<action id, or the i18n key of its label>` → why its icon does not say it alone. */
const PAINTED_LABELS: Readonly<Record<string, string>> = {
  'apps/kitchen/frontend/pages/StationsPage.vue#kitchen.routing.route':
    '«Route» sends a product or a category to a station: the swap arrows do not say it',
  'apps/kitchen/frontend/pages/StationsPage.vue#route': '«Route» of a station, the same action and icon as the list’s main one',
  'apps/payment/frontend/pages/PaymentsPage.vue#advance':
    'the next step changes with the payment (Approve, Mark as sent, Mark as completed): one icon cannot say which',
  'apps/printing/frontend/pages/JobsPage.vue#retry': '«Try again» has no icon of its own (a refresh arrow reloads)',
  'base/frontend/lib/apps-table.ts#plans': '«See plans» has no icon of its own',
  'base/frontend/lib/apps-table.ts#retry': '«Try again» has no icon of its own (a refresh arrow reloads)',
};

const ICON_ALONE =
  'a row action with an icon shows the icon alone (its label is its accessible name and tooltip): drop `showLabel`, ' +
  'or, if no icon says the action, add it to PAINTED_LABELS with the reason';

const nameOf = (name: ts.Node): string | undefined =>
  ts.isIdentifier(name) || ts.isStringLiteral(name) ? name.text : undefined;

/** The value of the property `name` of `action`, as written. */
function propertyOf(action: ts.ObjectLiteralExpression, name: string): ts.Expression | undefined {
  const found = action.properties.find((p) => ts.isPropertyAssignment(p) && nameOf(p.name) === name) as
    | ts.PropertyAssignment
    | undefined;
  return found && bare(found.initializer);
}

/** The i18n key of a label written as `t('<key>')`. */
function labelKey(label: ts.Expression | undefined): string | undefined {
  if (!label || !ts.isCallExpression(label)) return undefined;
  const [key] = label.arguments;
  return key && ts.isStringLiteralLike(key) ? key.text : undefined;
}

/** The literal `id` of the action `node` (a property of it) belongs to, else the i18n key of its label (a list's main
 *  action has no id); `?` when it is written as neither. */
function actionId(node: ts.Node): string {
  const action = node.parent;
  if (!ts.isObjectLiteralExpression(action)) return '?';
  const id = propertyOf(action, 'id');
  if (id && ts.isStringLiteralLike(id)) return id.text;
  return labelKey(propertyOf(action, 'label')) ?? '?';
}

/** Whether `node` paints its action's label: a `showLabel` that is not a written `false`. */
function paintsLabel(node: ts.Node): boolean {
  if (ts.isShorthandPropertyAssignment(node)) return node.name.text === 'showLabel';
  if (!ts.isPropertyAssignment(node) || nameOf(node.name) !== 'showLabel') return false;
  return bare(node.initializer).kind !== ts.SyntaxKind.FalseKeyword;
}

/** The ids of the actions of `text` (the file `name`) that paint their label. */
export function paintedIds(text: string, name: string): string[] {
  if (!text.includes('showLabel')) return [];
  return scriptBlocks(text, name).flatMap(({ code }) => {
    const file = ts.createSourceFile(name, code, ts.ScriptTarget.Latest, true);
    const ids: string[] = [];
    const visit = (node: ts.Node): void => {
      if (paintsLabel(node)) ids.push(actionId(node));
      ts.forEachChild(node, visit);
    };
    visit(file);
    return ids;
  });
}

/** The lines of `text` (the file `file`) whose action paints its label without being an exception. */
export function paintedLabels(text: string, file: string, exceptions = PAINTED_LABELS): number[] {
  if (!text.includes('showLabel')) return [];
  const where = relative(HUB, file);
  return linesWhere(text, file, (node) => paintsLabel(node) && !(`${where}#${actionId(node)}` in exceptions));
}

describe('guardrail: a row action with an icon shows the icon alone', () => {
  it('finds every action that paints its label, and lets the exceptions be', () => {
    const planted = [
      "const a = [{ id: 'open', label: 'Open', icon: 'open-outline', showLabel: true }];",
      "const b = [{ id: 'charge', icon: 'cash-outline', showLabel: id === 'charge' }];",
      'const c = [{ id, icon, showLabel }];',
      "const d = [{ id: 'edit', icon: 'create-outline', showLabel: false }];",
      "const e = [{ id: 'edit', icon: 'create-outline' }];",
      "const f = [{ id: 'retry', label: 'Retry', icon: 'refresh-outline', showLabel: true }];",
      '// A comment that says showLabel: true paints nothing.',
      "const g = computed(() => ({ label: t('demo.items.route'), icon: 'swap-horizontal-outline', showLabel: true }));",
    ].join('\n');
    const file = join(HUB, 'apps', 'demo', 'frontend', 'Planted.ts');
    expect(paintedLabels(planted, file, { 'apps/demo/frontend/Planted.ts#retry': 'planted' })).toEqual([1, 2, 3, 8]);
    expect(paintedIds(planted, file)).toEqual(['open', 'charge', '?', 'retry', 'demo.items.route']);
    const component = ['<template><DataTable :actions="actions" /></template>', '<script setup lang="ts">', planted, '</script>'];
    expect(paintedLabels(component.join('\n'), file.replace('.ts', '.vue'), {})).toEqual([3, 4, 5, 8, 10]);
  });

  it('no action of base or of an app paints its label unless it is an exception', async () => {
    expect(await findingsByApp(hubFrontends({ ui: false }), paintedLabels), ICON_ALONE).toEqual({});
  }, NO_CLOCK);

  it('every exception is still there: the list only shrinks', () => {
    const gone = Object.keys(PAINTED_LABELS).filter((entry) => {
      const [path, id] = entry.split('#');
      return !paintedIds(readFileSync(join(HUB, path), 'utf8'), path).includes(id);
    });
    expect(gone, 'strike the exceptions that no longer paint their label off PAINTED_LABELS').toEqual([]);
  });
});
