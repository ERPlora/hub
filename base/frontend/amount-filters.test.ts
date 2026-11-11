// base-amount-filter-one-reader (hub#1196): every list of the Hub reads an amount filter «from / to» one way, the way
// every money field reads an amount — the platform's `parseMoney`, through `filterCents` and `amountFilterErrors` of
// `lib/money.ts` — and says under an end it cannot read what the money field says. Each app's copy of its own read the
// same text as it pleased: «1.000,50» filtered from 1.000,50 € in one list and was «not an amount» in the next, «1.000»
// was 1.000 € in one and asked in another. A reader of its own is a function like any other, so this guard does not
// hunt for it: it makes every list with an amount filter (a table column or panel filter `{ type: 'range', amount:
// true }`) run the table of texts of `__tests__/amount-filter.ts` in its own test, where a reader of its own fails.
// The lists that do not yet are named here with the issue that takes them to it.
import { existsSync, readFileSync } from 'node:fs';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { bare, findingsByApp, HUB, hubFrontends, linesWhere } from './__tests__/frontend-sources';

/** The lists with an amount filter whose test does not run the table yet, and the issue that takes each to it. */
const NOT_YET: Record<string, string> = {
  // Fiscal app, worked with Ioan supervising (working-rules §15).
  'apps/verifactu/frontend/pages/RecordsPage.vue': 'hub#1247',
};

const RUN_THE_TABLE =
  "read the amount filter with filterCents and amountFilterErrors of base/frontend/lib/money.ts and run the table in the list's test: " +
  'itReadsAmountFiltersAsTheHub of base/frontend/__tests__/amount-filter.ts';

/** The name of a property when it is written as one (`amount`, `'amount'`). */
function nameOf(name: ts.Node): string | undefined {
  return ts.isIdentifier(name) || ts.isStringLiteral(name) ? name.text : undefined;
}

/** Whether `node` is a filter of an amount range: `{ type: 'range', amount: true, … }`. */
function amountRange(node: ts.Node): boolean {
  if (!ts.isObjectLiteralExpression(node)) return false;
  const value = (name: string) => {
    const property = node.properties.find((p): p is ts.PropertyAssignment => ts.isPropertyAssignment(p) && nameOf(p.name) === name);
    return property && bare(property.initializer);
  };
  const type = value('type');
  const amount = value('amount');
  return !!type && ts.isStringLiteralLike(type) && type.text === 'range' && amount?.kind === ts.SyntaxKind.TrueKeyword;
}

/** The lines of `text` (a `.ts`, or a `.vue` whose `<script>` blocks are read) with a filter of an amount range. */
export function amountRanges(text: string, name: string): number[] {
  return /\bamount\b/.test(text) ? linesWhere(text, name, amountRange) : [];
}

/** Whether the test next to `file` (`<name>.test.ts`) runs the table of texts. */
function runsTheTable(file: string): boolean {
  const test = file.replace(/\.(vue|ts)$/, '.test.ts');
  return existsSync(test) && /\bitReadsAmountFiltersAsTheHub\(/.test(readFileSync(test, 'utf8'));
}

describe('guardrail: every amount filter of the Hub is read as the money field reads an amount (base-amount-filter-one-reader)', () => {
  it('finds a filter of an amount range however it is written, and nothing else', () => {
    const planted = [
      "const a = { key: 'total', filter: { type: 'range', amount: true, keys: ['total_min', 'total_max'] } };",
      "const b = (keys) => ({ type: 'range' as const, amount: true, keys });",
      "const c = { 'type': ('range' as const), 'amount': true };",
      // A range of numbers, an amount that is no filter, a range said false, a comment.
      "const d = { type: 'range', keys: ['items_min', 'items_max'] };",
      "const e = { amount: true, label: 'Total' };",
      "const f = { type: 'range', amount: false };",
      "// { type: 'range', amount: true }",
    ].join('\n');
    expect(amountRanges(planted, 'salesFilters.ts')).toEqual([1, 2, 3]);
    const page = ['<template><DataTable /></template>', '<script setup lang="ts">', "const column = { filter: { type: 'range', amount: true } };", '</script>'];
    expect(amountRanges(page.join('\n'), 'CartsPage.vue')).toEqual([3]);
  });

  it('every list with an amount filter runs the table of texts in its own test', () => {
    const lists = findingsByApp(hubFrontends({ ui: false }), amountRanges);
    const files = [...new Set(Object.values(lists).flat().map((where) => where.replace(/:\d+$/, '')))];
    // The guard sees the lists it is about (one in each app that filters an amount).
    expect(files.length).toBeGreaterThanOrEqual(8);
    const missing = files.filter((file) => !(file in NOT_YET) && !runsTheTable(`${HUB}/${file}`));
    const done = Object.keys(NOT_YET).filter((file) => runsTheTable(`${HUB}/${file}`) || !files.includes(file));
    expect({ missing, done }, RUN_THE_TABLE).toEqual({ missing: [], done: [] });
  }, 60_000);
});
