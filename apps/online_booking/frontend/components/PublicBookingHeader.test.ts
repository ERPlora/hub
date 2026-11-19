import { describe, expect, it } from 'vitest';

import type { PageOut } from '../operations';
import { mountOnlineBooking } from '../__tests__/mount-online-booking';
import PublicBookingHeader from './PublicBookingHeader.vue';

const INFO = {
  business_name: 'Salón Lucía',
  title: 'Book an appointment',
  welcome_message: 'We look forward to seeing you.',
  logo_url: 'https://example.com/logo.png',
} as PageOut;

async function setup(locale: 'en' | 'es' = 'en', info = INFO) {
  return mountOnlineBooking(PublicBookingHeader, { props: { info }, locale });
}

describe('PublicBookingHeader', () => {
  it('shows whose page it is, with its logo, title and welcome', async () => {
    const s = await setup();
    expect(s.inDoc('ob-preview-business-name')?.textContent).toBe('Salón Lucía');
    expect(s.inDoc('ob-preview-title')?.textContent).toBe('Book an appointment');
    expect(s.wrapper.text()).toContain('We look forward to seeing you.');
    expect(s.inDoc('ob-preview-business-logo')?.getAttribute('alt')).toBe('Salón Lucía logo');
  });

  it('leaves out a missing logo and speaks Spanish', async () => {
    const s = await setup('es', { ...INFO, logo_url: '' });
    expect(s.inDoc('ob-preview-business-logo')).toBeNull();
    expect(s.wrapper.text()).not.toContain('undefined');
  });
});
