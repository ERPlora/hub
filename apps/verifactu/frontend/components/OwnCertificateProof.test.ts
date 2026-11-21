import { describe, expect, it } from 'vitest';

import { LOADED_CERTIFICATE } from '../__tests__/config-fixture';
import { mountVerifactu } from '../__tests__/mount-verifactu';
import type { ConfigOut } from '../operations';
import OwnCertificateProof from './OwnCertificateProof.vue';

async function setup(proof: ConfigOut['own_certificate']['aeat_proof']) {
  const m = await mountVerifactu(OwnCertificateProof, {
    props: { certificate: { ...LOADED_CERTIFICATE, aeat_proof: proof }, testid: 'certificate-proof' },
  });
  return m.find('certificate-proof');
}

describe('OwnCertificateProof', () => {
  it.each([
    { proof: 'untested' as const, label: 'Not tested yet' },
    { proof: 'accepted' as const, label: 'Accepted' },
    { proof: 'rejected' as const, label: 'Refused' },
  ])('says what the AEAT test environment made of it: $label', async ({ proof, label }) => {
    expect((await setup(proof)).text()).toBe(label);
  });
});
