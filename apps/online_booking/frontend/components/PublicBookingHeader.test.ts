import { describe, expect, it } from 'vitest';

import type { PageOut } from '../operations';
import { mountOnlineBooking } from '../__tests__/mount-online-booking';
import PublicBookingHeader from './PublicBookingHeader.vue';

const INFO = {
  business_name: 'Salón Lucía',
  title: 'Book an appointment',
  welcome_message: 'We look forward to seeing you.',
  logo_url: '/media/logo.png',
} as PageOut;

async function setup(locale: 'en' | 'es' = 'en', info = INFO) {
  return mountOnlineBooking(PublicBookingHeader, { props: { info }, locale });
}

describe('PublicBookingHeader', () => {
  it.each(['/media/logo.png', `${window.location.origin}/logo.png`])('shows a same-origin logo: %s', async (logoUrl) => {
    const s = await setup('en', { ...INFO, logo_url: logoUrl });
    expect(s.inDoc('ob-preview-business-name')?.textContent).toBe('Salón Lucía');
    expect(s.inDoc('ob-preview-title')?.textContent).toBe('Book an appointment');
    expect(s.wrapper.text()).toContain('We look forward to seeing you.');
    expect(s.inDoc('ob-preview-business-logo')?.getAttribute('alt')).toBe('Salón Lucía logo');
  });

  it.each(['https://example.com/logo.png', '//example.com/logo.png', 'data:image/png;base64,AA=='])('leaves out an image the page cannot load: %s', async (logoUrl) => {
    const s = await setup('en', { ...INFO, logo_url: logoUrl });
    expect(s.inDoc('ob-preview-business-logo')).toBeNull();
    expect(s.inDoc('ob-preview-business-name')?.textContent).toBe('Salón Lucía');
    expect(s.inDoc('ob-preview-title')?.textContent).toBe('Book an appointment');
  });

  it('leaves out a missing logo and speaks Spanish', async () => {
    const s = await setup('es', { ...INFO, logo_url: '' });
    expect(s.inDoc('ob-preview-business-logo')).toBeNull();
    expect(s.wrapper.text()).not.toContain('undefined');
  });
});
