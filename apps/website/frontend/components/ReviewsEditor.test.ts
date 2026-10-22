// ReviewsEditor: the business on Google Maps (its link, a share link or its Place ID) and a note that says whether
// Google's rating and reviews are there: none yet, not on this server, Google failed, ready, or to be read once saved.
import { describe, expect, it } from 'vitest';

import { ionValue, mountWebsite, OWNER } from '../__tests__/mount-website';
import type { ReviewsStatusOut } from '../operations';
import ReviewsEditor from './ReviewsEditor.vue';

const PLACE = 'https://maps.app.goo.gl/AbCdEf123';
const status = (overrides: Partial<ReviewsStatusOut> = {}): ReviewsStatusOut => ({
  state: 'waiting',
  rating: null,
  count: 0,
  fetched_at: null,
  ...overrides,
});

async function editor(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const { wrapper } = await mountWebsite(ReviewsEditor, {
    props: { modelValue: PLACE, status: status(), ...props },
    locale,
    session: { ...OWNER, language: locale },
  });
  const field = () => wrapper.get('[data-testid="website-field-reviews-place_ref"]').element as HTMLElement & {
    value?: string;
    label?: string;
    helperText?: string;
    errorText?: string;
  };
  const note = () => wrapper.get('[data-testid="website-reviews-status"]');
  return { wrapper, field, note };
}

describe('ReviewsEditor', () => {
  it('asks for the link of the business on Google Maps and says how to get it', async () => {
    const { field } = await editor();
    expect(field().value).toBe(PLACE);
    expect(field().label).toBe('Google Maps link or Place ID');
    expect(field().helperText).toBe('On Google Maps, open your business, press Share and paste its link here.');
  });

  it('emits what is typed', async () => {
    const { wrapper } = await editor();
    await ionValue(wrapper.get('[data-testid="website-field-reviews-place_ref"]').element, 'ChIJN1t_tDeuEmsRUsoyG83frY4', 'ionInput');
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['ChIJN1t_tDeuEmsRUsoyG83frY4']);
  });

  it.each([
    ['empty', 'Paste the link to show your rating and reviews from Google.'],
    ['waiting', 'Your reviews will show here and on your page once Google answers for this place.'],
    ['failed', 'Google did not answer for this place. Check the link: it will be tried again in a few minutes.'],
    ['unavailable', 'Google reviews are not available yet: your link is kept and they will show as soon as they are.'],
  ] as const)('says where the reviews are: %s', async (state, text) => {
    const { note } = await editor({ status: status({ state }) });
    expect(note().element.textContent).toContain(text);
    expect(note().attributes('data-state')).toBe(state);
  });

  it('ready: Google’s rating and count, in the person’s language', async () => {
    const ready = status({ state: 'ready', rating: 4.7, count: 1280, fetched_at: '2026-10-22T09:00:00Z' });
    expect((await editor({ status: ready })).note().element.textContent).toContain('Rating 4.7 out of 5 · reviews on Google: 1,280');
    expect((await editor({ status: ready }, 'es')).note().element.textContent).toContain(
      'Valoración 4,7 de 5 · reseñas en Google: 1280',
    );
  });

  it('a link not saved yet is read once it is', async () => {
    const { note } = await editor({ status: status({ state: 'ready', rating: 4.7, count: 3 }), changed: true });
    expect(note().attributes('data-state')).toBe('changed');
    expect(note().element.textContent).toContain('Google will be asked for this place once it is saved.');
  });

  it('shows the server’s refusal on the field', async () => {
    const message = 'Paste the link of your business on Google Maps, or its Place ID.';
    const { field } = await editor({ error: message });
    expect(field().errorText).toBe(message);
    expect(field().classList.contains('ion-invalid')).toBe(true);
  });

  it('a disabled field changes nothing', async () => {
    const { wrapper } = await editor({ disabled: true });
    await ionValue(wrapper.get('[data-testid="website-field-reviews-place_ref"]').element, 'x', 'ionInput');
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const { field, note } = await editor({ status: status({ state: 'empty' }) }, 'es');
    expect(field().label).toBe('Enlace de Google Maps o Place ID');
    expect(note().element.textContent).toContain('Pega el enlace para mostrar tu valoración y tus reseñas de Google.');
  });
});
