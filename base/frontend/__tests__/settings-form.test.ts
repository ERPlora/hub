// The checks every settings page's tests share (hub#897): where a notice sits, Enter in a field, and what a refused
// field shows.
import { describe, expect, it } from 'vitest';

import { between, pressEnter, refusalMarks } from './settings-form';

/** A form with three children, in this order: a field, a notice and «Save». */
function page() {
  const form = document.createElement('form');
  const [field, notice, save] = ['field', 'notice', 'save'].map((name) => {
    const el = document.createElement('div');
    el.dataset.name = name;
    form.append(el);
    return el;
  });
  return { form, field, notice, save };
}

describe('settings form checks (hub#897)', () => {
  it('between: true only when the middle one comes after the first and before the last', () => {
    const { field, notice, save } = page();
    expect([between(field, notice, save), between(notice, field, save), between(field, save, notice)]).toEqual([true, false, false]);
  });

  it('pressEnter submits the form once, as Ionic’s hidden submit button does', async () => {
    const { form } = page();
    const submits: Event[] = [];
    form.addEventListener('submit', (event) => submits.push(event));
    await pressEnter(form);
    expect(submits.map((event) => event.cancelable)).toEqual([true]);
  });

  it('pressEnter without a form says so instead of passing', async () => {
    await expect(pressEnter(null)).rejects.toThrow('no settings form');
  });

  it('refusalMarks reads the notice with the page’s probe, and a field’s message and its mark', () => {
    const [refused, fine] = [document.createElement('ion-input'), document.createElement('ion-input')];
    Object.assign(refused, { errorText: 'Too long.' });
    refused.classList.add('ion-invalid');
    let shown = true;
    const { notice, says, marked } = refusalMarks((name) => (name === 'refused' ? refused : fine), () => shown);
    expect([notice(), says('refused'), marked('refused'), says('fine'), marked('fine')]).toEqual([true, 'Too long.', true, '', false]);
    shown = false;
    expect(notice()).toBe(false);
  });
});
