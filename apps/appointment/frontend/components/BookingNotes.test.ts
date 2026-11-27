// The notes of the booking panel (APPOINTMENT-F01, F22): «Notes for the customer» and «Internal notes», folded until
// they are asked for. A note with text comes open, and a refusal of a folded one opens it with its reason.
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountAppointment, settle } from '../__tests__/mount-appointment';
import BookingNotes from './BookingNotes.vue';

type Area = HTMLElement & { value?: string; label?: string; errorText?: string };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(BookingNotes, { props: { notes: '', internalNotes: '', ...props }, locale });
  const area = (name: string) => m.inDoc(`appointment-form-${name}`) as Area | null;
  const toggle = (name: string) => m.find(`appointment-form-${name}-fold-toggle`);
  return { ...m, area, toggle };
}

describe('BookingNotes', () => {
  it('both come folded and empty, each saying it is optional', async () => {
    const s = await setup();
    expect([s.toggle('notes').text(), s.toggle('internal_notes').text()]).toEqual(['Notes for the customerOptional', 'Internal notesOptional']);
    expect([s.area('notes'), s.area('internal_notes')]).toEqual([null, null]);
  });

  it('opens one when asked, and what is typed is the note', async () => {
    const s = await setup();
    await click(s.toggle('internal_notes').element);
    expect(s.area('internal_notes')?.label).toBe('Internal notes');
    expect(s.area('notes')).toBeNull();
    await ionValue(s.area('internal_notes'), 'Warm water', 'ionInput');
    expect(s.wrapper.emitted('update:internalNotes')).toEqual([['Warm water']]);
  });

  it('a note with text comes open', async () => {
    const s = await setup({ notes: 'Bring photo' });
    expect(s.area('notes')?.value).toBe('Bring photo');
    expect(s.area('internal_notes')).toBeNull();
  });

  it('a refusal opens the folded note with its reason under it', async () => {
    const s = await setup();
    await s.wrapper.setProps({ internalNotesError: 'Too long.' });
    await settle();
    expect(s.area('internal_notes')?.errorText).toBe('Too long.');
    expect(s.area('notes')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.toggle('notes').text()).toBe('Notas para la clientaOpcional');
  });
});
