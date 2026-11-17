import { describe, expect, it } from 'vitest';

import { CONFIG, LOADED_CERTIFICATE } from '../__tests__/config-fixture';
import { mountVerifactu } from '../__tests__/mount-verifactu';
import type { ConfigOut } from '../operations';
import OwnCertificateStatus from './OwnCertificateStatus.vue';

async function setup(certificate: Partial<ConfigOut['own_certificate']>) {
  const m = await mountVerifactu(OwnCertificateStatus, {
    props: { certificate: { ...CONFIG.own_certificate, ...certificate }, testid: 'certificate-status' },
  });
  return m.find('certificate-status');
}

describe('OwnCertificateStatus', () => {
  it.each([
    { certificate: {}, label: 'No certificate uploaded' },
    { certificate: { ...LOADED_CERTIFICATE, expires_in_days: 351 }, label: 'Valid' },
    { certificate: { ...LOADED_CERTIFICATE, expires_in_days: 17 }, label: 'Expires soon' },
    { certificate: { ...LOADED_CERTIFICATE, expires_in_days: -1 }, label: 'Expired' },
  ])('shows the explicit status $label', async ({ certificate, label }) => {
    expect((await setup(certificate)).text()).toBe(label);
  });
});
