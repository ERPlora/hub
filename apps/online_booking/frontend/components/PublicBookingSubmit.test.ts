import { describe, expect, it } from 'vitest';

import { click, mountOnlineBooking } from '../__tests__/mount-online-booking';
import PublicBookingSubmit from './PublicBookingSubmit.vue';

async function setup(locale: 'en' | 'es' = 'en') {
  return mountOnlineBooking(PublicBookingSubmit, {
    props: {
      businessName: 'Salón Lucía',
      privacyPolicyUrl: 'https://erplora.com/legal/privacy/',
      ready: true,
      pending: false,
      website: '',
    },
    locale,
  });
}

describe('PublicBookingSubmit', () => {
  it('links the privacy policy and submits the form', async () => {
    const s = await setup();
    expect(s.inDoc('ob-preview-privacy')?.textContent).toContain('Salón Lucía will use your details');
    expect(s.inDoc('ob-preview-privacy')?.querySelector('a')?.getAttribute('href')).toBe('https://erplora.com/legal/privacy/');
    await click(s.inDoc('ob-preview-book'));
    expect(s.wrapper.emitted('submit')).toEqual([[]]);
  });

  it('keeps the trap off screen and away from keyboard and assistive technology', async () => {
    const s = await setup();
    const trap = s.inDoc('ob-preview-trap')!;
    const input = s.inDoc('ob-preview-trap-input') as HTMLInputElement;
    expect(trap.getAttribute('aria-hidden')).toBe('true');
    expect(input.tabIndex).toBe(-1);
    expect(input.getAttribute('autocomplete')).toBe('off');
    expect(trap.hidden).toBe(true);
    expect(trap.classList.contains('ob-public-submit__trap')).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('ob-preview-privacy')?.textContent).toContain('política de privacidad');
  });
});
