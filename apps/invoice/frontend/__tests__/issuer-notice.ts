// What a screen of Invoicing says about a missing issuer, in Spanish, as its tests check it: the platform's strip says
// once that nothing can be invoiced, the only red notice on the screen, with «Configurar» to the issuer's step for
// whoever may set it up and «an administrator has to» for anyone else; once the issuer is set, nothing says it.
import type { DOMWrapper } from '@vue/test-utils';
import { expect } from 'vitest';

import { type MountedInvoice, redNotices, said } from './mount-invoice';

function expectNothingInvoiceableSaidOnce(m: MountedInvoice): void {
  expect(said(m.wrapper.text(), 'Todavía no puedes facturar')).toBe(1);
  expect(redNotices(m)).toBe(1);
}

/** The screen says it with one «Configurar» to the issuer's step: returns that button. */
export function expectIssuerToSetUp(m: MountedInvoice): DOMWrapper<Element> {
  expectNothingInvoiceableSaidOnce(m);
  expect(said(m.wrapper.text(), 'Los datos de tu negocio')).toBe(1);
  const setUp = m.wrapper.findAll('ion-button').filter((b) => b.text() === 'Configurar');
  expect(setUp).toHaveLength(1);
  return setUp[0];
}

/** The screen says that an administrator has to set the issuer up, and offers no «Configurar». */
export function expectAnAdministratorToSetUpTheIssuer(m: MountedInvoice): void {
  expectNothingInvoiceableSaidOnce(m);
  expect(said(m.wrapper.text(), 'Esto lo tiene que configurar un administrador.')).toBe(1);
  expect(m.wrapper.findAll('ion-button').filter((b) => b.text() === 'Configurar')).toHaveLength(0);
}

export function expectIssuerSaidNoMore(m: MountedInvoice): void {
  expect(said(m.wrapper.text(), 'Todavía no puedes facturar')).toBe(0);
  expect(redNotices(m)).toBe(0);
}
