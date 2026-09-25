// hub#2074 — a person's PIN is a secret: it is typed masked in Employees, like in My profile.
//
// Both entry points typed the PIN into a plain text `ion-input`, so the six digits stayed readable
// on screen (and in any recording or shared screen) while the manager typed them. The quick
// "New" panel of the list and the full employee form must both mask it, keep the numeric keypad,
// offer the eye to reveal it, and ask the browser NOT to autofill a saved password into it.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const sources = {
  'EmployeesPage.vue': readFileSync(new URL('./EmployeesPage.vue', import.meta.url), 'utf8'),
  'EmployeeFormPage.vue': readFileSync(new URL('./EmployeeFormPage.vue', import.meta.url), 'utf8'),
};

/** The full `<ion-input …>…</ion-input>` (or self-closed) element that carries `testId`. */
function inputElement(source: string, testId: string): string {
  const marker = source.indexOf(`data-testid="${testId}"`);
  expect(marker, `${testId} not found`).toBeGreaterThan(-1);
  const start = source.lastIndexOf('<ion-input', marker);
  const openEnd = source.indexOf('>', marker);
  if (source[openEnd - 1] === '/') return source.slice(start, openEnd + 1);
  return source.slice(start, source.indexOf('</ion-input>', openEnd) + '</ion-input>'.length);
}

describe.each([
  ['EmployeesPage.vue', 'employees-pin'],
  ['EmployeeFormPage.vue', 'employee-pin'],
] as const)('%s PIN field (hub#2074)', (file, testId) => {
  const element = inputElement(sources[file], testId);

  it('masks the digits while typing', () => {
    expect(element).toMatch(/\stype="password"/);
  });

  it('keeps the numeric keypad', () => {
    expect(element).toMatch(/\sinputmode="numeric"/);
  });

  it('does not let the browser autofill a saved password into it', () => {
    expect(element).toMatch(/\sautocomplete="new-password"/);
  });

  it('offers the eye to reveal what was typed', () => {
    expect(element).toContain('<ion-input-password-toggle slot="end"');
  });
});
