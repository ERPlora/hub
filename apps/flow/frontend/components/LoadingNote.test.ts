// «Loading…» while what a screen needs is still being read (WORKBOOK «Estados de cada pantalla · Cargando»): read out
// by a screen reader as a status, the dots are decoration. The page and «Which data?» say it with this one line.
import { describe, expect, it } from 'vitest';

import { mountFlow, settle } from '../__tests__/mount-flow';
import LoadingNote from './LoadingNote.vue';

describe('LoadingNote', () => {
  it('says «Loading…» as a status, with its dots hidden from a screen reader', async () => {
    const m = await mountFlow(LoadingNote);
    await settle();
    const note = m.wrapper.find('[role="status"]');
    expect(note.text()).toBe('Loading…');
    expect(note.find('ion-spinner').attributes('aria-hidden')).toBe('true');
  });

  it('says it in the person\'s language', async () => {
    const m = await mountFlow(LoadingNote, { locale: 'es' });
    await settle();
    expect(m.wrapper.find('[role="status"]').text()).toBe('Cargando…');
  });
});
