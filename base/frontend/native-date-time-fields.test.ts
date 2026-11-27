// The Hub never opens the device's own date or time picker. A native `<input type="date">` (also inside an `ion-input`
// of that type, `time` or `datetime-local`) is painted by the system: on Android, a green dialog in the device's
// language, outside the page and the business's theme. Every day and time of the Hub is picked with DateField,
// TimeField or DateTimeField of @erplora/ui, which open Ionic's calendar in the app's palette and language. This guard
// reads the templates of base, of each app and of the shared `ui`, and there may be none left: a type written in the
// template (`type="date"`, `type=time`) or a bound one that names it (`:type="kind === 'day' ? 'date' : 'text'"`).
import { describe, expect, it } from 'vitest';

import { findingsByApp, hubFrontends, templateLinesWhere } from './__tests__/frontend-sources';
import { NO_CLOCK } from '../../vitest.load';

const PICK_IT_IN_THE_APP =
  "pick a day or a time with DateField, TimeField or DateTimeField of @erplora/ui/components, never a native type='date|time|datetime-local'";

const NATIVE = '(?:date|time|datetime-local)';
/** A type written in the template, quoted or not. */
const WRITTEN = new RegExp(`(?:^|\\s)type=(?:"${NATIVE}"|'${NATIVE}'|${NATIVE}(?=[\\s/>]|$))`);
/** A bound type whose expression names one of them. */
const BOUND = new RegExp(`(?:^|\\s)(?::|v-bind:)type="[^"]*'${NATIVE}'[^"]*"`);

/** The lines of a component's template (its outermost `<template>`) that ask for a native date or time field. */
export function nativeDateTimeFields(text: string, name: string): number[] {
  return templateLinesWhere(text, name, (line) => WRITTEN.test(line) || BOUND.test(line));
}

describe('guardrail: no template of the Hub or of @erplora/ui opens the device’s own date or time picker', () => {
  it('finds a native date or time field however it is written, and nothing else', () => {
    const planted = [
      '<script setup lang="ts">',
      "const filter = { type: 'date' };",
      '</script>',
      '<template>',
      '  <ion-input type="date" />',
      "  <ion-input type='time' :value=\"at\" />",
      '  <input type=datetime-local>',
      '  <IonInput',
      '    type="time"',
      '  />',
      "  <ion-input :type=\"field === 'birthday' ? 'date' : 'text'\" />",
      "  <ion-input v-bind:type=\"'datetime-local'\" />",
      // Not a native date or time: other types, a filter's kind, attributes that only read like one.
      '  <ion-input type="text" />',
      '  <ion-input :type="field.type" />',
      "  <DataTable :columns=\"[{ key: 'day', filter: { type: 'date' } }]\" />",
      '  <DateField data-type="date" presentation="date" />',
      '</template>',
    ].join('\n');
    expect(nativeDateTimeFields(planted, 'Planted.vue')).toEqual([5, 6, 7, 9, 11, 12]);
    expect(nativeDateTimeFields('<ion-input type="date" />', 'notes.ts')).toEqual([]);
  });

  it('none is left in base, the apps or @erplora/ui', async () => {
    const found = await findingsByApp(hubFrontends({ ui: true }), nativeDateTimeFields);
    expect(found, PICK_IT_IN_THE_APP).toEqual({});
  }, NO_CLOCK);
});
