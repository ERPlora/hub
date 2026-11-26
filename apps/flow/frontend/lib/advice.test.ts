import { describe, expect, it } from 'vitest';

import { phrasingIn } from '../__tests__/phrasing';
import { advice, withAdvice } from './advice';

const EN = phrasingIn('en');

describe('advice', () => {
  it('says what to do about why a run stopped, in the reader’s language', () => {
    expect(advice('flow.not_allowed', EN)).toBe('Open Permissions and allow what it needs.');
    expect(advice('flow.not_allowed', phrasingIn('es'))).toBe('Abre Permisos y concédele lo que necesita.');
  });

  it('says nothing for a reason with nothing to add, or none', () => {
    expect(advice('flow.deleted', EN)).toBe('');
    expect(advice('', EN)).toBe('');
  });
});

describe('withAdvice', () => {
  it('follows what happened with what to do, once', () => {
    expect(withAdvice('It stopped.', 'flow.not_allowed', EN)).toBe('It stopped. Open Permissions and allow what it needs.');
  });

  it('leaves what happened alone when there is nothing to add', () => {
    expect(withAdvice('Cancelled.', 'flow.deleted', EN)).toBe('Cancelled.');
  });
});
