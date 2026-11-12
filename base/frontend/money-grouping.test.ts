// base-money-thousands-grouping (hub#692): the Hub writes an amount one way, its thousands grouped from four digits on
// («1.234,56 €», legacy hub#1090), with the platform's `formatMoney` (`@erplora/ui/components`, `format/money.ts`). A
// money formatter of an app's own keeps Intl's Spanish default, which waits for five digits: «1234,56 €» in one screen
// beside «1.234,56 €» in the next. This guard looks, by app (and `ui`, the shared package), for the currency formats
// that do not group always, and there may be none.
//
// What it looks for: every options object of an `Intl.NumberFormat` that says `style: 'currency'` in the sources of
// `apps/*/frontend`, `base/frontend` and `packages/ui/src` (`.ts` and the `<script>` of a `.vue`; tests and their
// helpers left out). One
// groups when `useGrouping: 'always'` is in it, in an object it spreads (`...digits`) or in the object that spreads it
// (`{ ...style, useGrouping: 'always' }`); and, as one branch of `money ? { style: 'currency', … } : digits`, when the
// figure written while the currency is unknown (the other branch) groups too. Not counted: the sign alone (a format
// whose `formatToParts` is searched for its `currency` part: «€», «zł»), and every number that is no amount (a quantity
// or a percentage has no `style: 'currency'`; what a person types in a money field is no format).
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { bare, findingsByApp, hubFrontends, scriptBlocks } from './__tests__/frontend-sources';
import { NO_CLOCK } from '../../vitest.load';

const GROUP_THE_AMOUNT =
  'write the amount with formatMoney of @erplora/ui/components (the platform\'s one way to write an amount), or ' +
  "give the format useGrouping: 'always'";

/** Whether `object` sets `name` to the string `value` (`style: 'currency'`, `useGrouping: 'always' as const`). */
function says(object: ts.ObjectLiteralExpression, name: string, value: string): boolean {
  return object.properties.some((property) => {
    if (!ts.isPropertyAssignment(property)) return false;
    if (!ts.isIdentifier(property.name) && !ts.isStringLiteral(property.name)) return false;
    const initializer = bare(property.initializer);
    return property.name.text === name && ts.isStringLiteralLike(initializer) && initializer.text === value;
  });
}

/** The function (or the file) whose names `node` sees first. */
function scopeOf(node: ts.Node): ts.Node {
  let current = node.parent;
  while (!ts.isFunctionLike(current) && !ts.isSourceFile(current)) current = current.parent;
  return current;
}

const within = (outer: ts.Node, inner: ts.Node) => inner.pos >= outer.pos && inner.end <= outer.end;

class Source {
  readonly file: ts.SourceFile;
  private readonly declarations = new Map<string, ts.VariableDeclaration[]>();
  private readonly spreads: ts.SpreadAssignment[] = [];
  readonly currencyFormats: ts.ObjectLiteralExpression[] = [];

  constructor(text: string, name: string) {
    this.file = ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true);
    const visit = (node: ts.Node): void => {
      if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
        this.declarations.set(node.name.text, [...(this.declarations.get(node.name.text) ?? []), node]);
      } else if (ts.isSpreadAssignment(node)) {
        this.spreads.push(node);
      } else if (ts.isObjectLiteralExpression(node) && says(node, 'style', 'currency')) {
        this.currencyFormats.push(node);
      }
      ts.forEachChild(node, visit);
    };
    visit(this.file);
  }

  /** The declaration `name` stands for where `at` reads it: the one of the innermost scope that holds `at`. */
  private declared(name: string, at: ts.Node): ts.VariableDeclaration | undefined {
    const seen = (this.declarations.get(name) ?? []).filter((declaration) => within(scopeOf(declaration), at));
    return seen.sort((a, b) => scopeOf(a).end - scopeOf(a).pos - (scopeOf(b).end - scopeOf(b).pos))[0];
  }

  /** The object literals `expression` may be: itself, either branch of a condition, what a name was given. */
  private objectsOf(expression: ts.Expression, seen: Set<ts.Node>): ts.ObjectLiteralExpression[] {
    const node = bare(expression);
    if (seen.has(node)) return [];
    seen.add(node);
    if (ts.isObjectLiteralExpression(node)) return [node];
    if (ts.isConditionalExpression(node)) return [...this.objectsOf(node.whenTrue, seen), ...this.objectsOf(node.whenFalse, seen)];
    if (ts.isIdentifier(node)) {
      const initializer = this.declared(node.text, node)?.initializer;
      return initializer ? this.objectsOf(initializer, seen) : [];
    }
    return [];
  }

  /** Whether `object` groups always: by itself, or by an object it spreads. */
  private groups(object: ts.ObjectLiteralExpression, seen = new Set<ts.Node>()): boolean {
    if (says(object, 'useGrouping', 'always')) return true;
    return object.properties.some(
      (property) => ts.isSpreadAssignment(property) && this.objectsOf(property.expression, seen).some((inner) => this.groups(inner, seen)),
    );
  }

  /** The expression `object` is a part of (through parentheses, `as` and the branches of a condition), and its branches. */
  private holderOf(object: ts.ObjectLiteralExpression): { holder: ts.Expression; others: ts.Expression[] } {
    let holder: ts.Expression = object;
    const others: ts.Expression[] = [];
    for (;;) {
      const parent = holder.parent;
      if (ts.isParenthesizedExpression(parent) || ts.isAsExpression(parent) || ts.isSatisfiesExpression(parent)) {
        holder = parent;
      } else if (ts.isConditionalExpression(parent) && parent.condition !== holder) {
        others.push(parent.whenTrue === holder ? parent.whenFalse : parent.whenTrue);
        holder = parent;
      } else {
        return { holder, others };
      }
    }
  }

  /** Whether an object that spreads `holder` (inline, or by the name it was given) groups always. */
  private spreadIntoGrouping(holder: ts.Expression): boolean {
    const parent = holder.parent;
    if (ts.isSpreadAssignment(parent)) return this.groups(parent.parent);
    if (!ts.isVariableDeclaration(parent) || !ts.isIdentifier(parent.name)) return false;
    const name = parent.name.text;
    return this.spreads.some((spread) => {
      const target = bare(spread.expression);
      return ts.isIdentifier(target) && target.text === name && this.declared(name, target) === parent && this.groups(spread.parent);
    });
  }

  /** Whether `object` only gives the sign: its format's parts are searched for the `currency` one («€», «zł»). */
  isSign(object: ts.ObjectLiteralExpression): boolean {
    let node: ts.Node = object;
    while (!ts.isFunctionLike(node.parent) && !ts.isSourceFile(node.parent)) {
      const parent = node.parent;
      if ((ts.isCallExpression(parent) || ts.isNewExpression(parent)) && parent.arguments?.some((argument) => argument === node)) {
        const parts = parent.parent;
        if (!ts.isPropertyAccessExpression(parts) || parts.name.text !== 'formatToParts' || !ts.isCallExpression(parts.parent)) return false;
        const find = parts.parent.parent;
        if (!ts.isPropertyAccessExpression(find) || find.name.text !== 'find' || !ts.isCallExpression(find.parent)) return false;
        return find.parent.arguments.some((argument) => /\.type\s*===\s*['"]currency['"]/.test(argument.getText(this.file)));
      }
      node = parent;
    }
    return false;
  }

  /** Whether the amounts `object` writes group always, and the figure of its other branch while the money is unknown. */
  groupsAlways(object: ts.ObjectLiteralExpression): boolean {
    const { holder, others } = this.holderOf(object);
    if (this.spreadIntoGrouping(holder)) return true;
    if (!this.groups(object)) return false;
    return others.every((other) => this.objectsOf(other, new Set()).every((inner) => inner.properties.length === 0 || this.groups(inner)));
  }

  line(node: ts.Node): number {
    return this.file.getLineAndCharacterOfPosition(node.getStart(this.file)).line + 1;
  }
}

/** A file that never writes `style: 'currency'` has no currency format: it is not parsed. */
const CURRENCY_STYLE = /['"`]?style['"`]?\s*:\s*['"`]currency['"`]/;

/** The lines of `text` (a `.ts`, or a `.vue` whose `<script>` blocks are read) with a currency format that does not
 *  group always. */
export function ungroupedFormats(text: string, name: string): number[] {
  if (!CURRENCY_STYLE.test(text)) return [];
  return scriptBlocks(text, name).flatMap(({ code, offset }) => {
    const source = new Source(code, name.endsWith('.vue') ? `${name}.ts` : name);
    return source.currencyFormats
      .filter((object) => !source.isSign(object) && !source.groupsAlways(object))
      .map((object) => source.line(object) + offset);
  });
}

/** Every currency format of the Hub's frontends (and of the shared `@erplora/ui`) that does not group always, as
 *  `<path>:<line>`, by app. */
function ungroupedByApp(): Record<string, string[]> {
  return findingsByApp(hubFrontends({ ui: true }), ungroupedFormats);
}

describe('guardrail: every amount of the Hub groups its thousands (base-money-thousands-grouping)', () => {
  it('counts a currency format that keeps Intl’s default, and none that groups always or only gives the sign', () => {
    const planted = [
      // Intl's default (Spanish waits for five digits), and its fallback: lines 1 and 2.
      "const a = new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' });",
      "const b = new Intl.NumberFormat('en', { style: 'currency', currency: 'EUR' });",
      // Groups by itself.
      "const c = new Intl.NumberFormat(locale, { style: 'currency', currency, useGrouping: 'always' });",
      // Groups by what it spreads, and so does the figure of its other branch.
      'function options(money, decimals) {',
      "  const digits = { minimumFractionDigits: decimals, useGrouping: 'always' as const };",
      "  return money ? { style: 'currency', currency: money.currency, ...digits } : digits;",
      '}',
      // Its digits do not group: line 10.
      'function plain(money, decimals) {',
      '  const digits = { minimumFractionDigits: decimals };',
      "  return money ? { style: 'currency', currency: money.currency, ...digits } : digits;",
      '}',
      // Groups, but not the figure written while the money is unknown («1234,56»): line 14.
      'function half(money) {',
      '  const digits = { minimumFractionDigits: 2 };',
      "  return money ? { style: 'currency', currency: money.currency, ...digits, useGrouping: 'always' } : digits;",
      '}',
      // Grouped by the object that spreads it (by its name, or inline).
      'function spread(money) {',
      "  const style = money ? { style: 'currency', currency: money.currency } : {};",
      "  return new Intl.NumberFormat(locale, { ...style, minimumFractionDigits: 2, useGrouping: 'always' });",
      '}',
      "const d = new Intl.NumberFormat(locale, { ...(money ? { style: 'currency', currency } : {}), useGrouping: 'always' });",
      // Spread into one that does not group: line 22.
      'function spreadPlain(money) {',
      "  const style = money ? { style: 'currency', currency: money.currency } : {};",
      '  return new Intl.NumberFormat(locale, { ...style, minimumFractionDigits: 2 });',
      '}',
      // The sign alone, and a quantity: no amount.
      "const sign = new Intl.NumberFormat('en', { style: 'currency', currency, currencyDisplay }).formatToParts(1).find((part) => part.type === 'currency')?.value;",
      "const signOf = formatter(locale, 'sign', { style: 'currency', currency }).formatToParts(0).find((part) => part.type === 'currency');",
      'const quantity = new Intl.NumberFormat(locale, { maximumFractionDigits: 3, useGrouping: false });',
      // Its parts are searched for another thing, so it writes the amount: line 28.
      "const parts = new Intl.NumberFormat(locale, { style: 'currency', currency }).formatToParts(5).find((part) => part.type === 'integer');",
    ].join('\n');
    expect(ungroupedFormats(planted, 'format.ts')).toEqual([1, 2, 10, 14, 22, 28]);
    // A component's script, at its own line of the file.
    const component = ['<template>{{ total }}</template>', '<script setup lang="ts">', "const f = new Intl.NumberFormat('es', { style: 'currency', currency: 'EUR' });", '</script>'];
    expect(ungroupedFormats(component.join('\n'), 'Total.vue')).toEqual([3]);
  });

  it('no app, nor base or `ui`, has a currency format that does not group always', () => {
    expect(ungroupedByApp(), GROUP_THE_AMOUNT).toEqual({});
    // It reads every frontend file of the Hub (some 1,600), synchronously: as long as the machine makes it (hub#1200).
  }, NO_CLOCK);
});
