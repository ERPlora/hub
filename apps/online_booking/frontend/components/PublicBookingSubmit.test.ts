import { describe, expect, it } from 'vitest';

import { click, mountOnlineBooking } from '../__tests__/mount-online-booking';
import PublicBookingSubmit from './PublicBookingSubmit.vue';

async function setup(locale: 'en' | 'es' = 'en', businessName = 'Salón Lucía') {
  return mountOnlineBooking(PublicBookingSubmit, {
    props: {
      businessName,
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
    expect(s.inDoc('ob-preview-privacy')?.textContent).toContain('Your details will be used by Salón Lucía to manage this booking');
    expect(s.inDoc('ob-preview-privacy')?.textContent).toContain('on behalf of Salón Lucía');
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

  it('uses a grammatical fallback when a demo has no registered business name', async () => {
    const s = await setup('en', '');
    const notice = s.inDoc('ob-preview-privacy')?.textContent;
    expect(notice).toContain('Your details will be used by the business to manage this booking');
    expect(notice).toContain('on behalf of the business');
  });

  it('speaks Spanish with the business as the controller and ERPlora acting for it', async () => {
    const s = await setup('es');
    const notice = s.inDoc('ob-preview-privacy')?.textContent;
    expect(notice).toContain('Salón Lucía usará tus datos para gestionar esta reserva');
    expect(notice).toContain('ERPlora los tratará por encargo de Salón Lucía');
    expect(notice).toContain('política de privacidad');
    expect(notice).not.toContain('por su cuenta');
  });
});
