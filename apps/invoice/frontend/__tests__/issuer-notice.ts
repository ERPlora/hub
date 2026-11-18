// What a screen of Invoicing says about a missing issuer, in Spanish, as its tests check it: the screen itself says
// nothing; the hub's action center has the one «Todavía no puedes facturar», with «Configurar los datos del negocio» to
// the issuer's step for whoever may set it up and «an administrator has to» for anyone else; once the issuer is set,
// nothing says it.
import type { ActionNotice, NoticeAction } from '@erplora/ui/shell';
import { expect } from 'vitest';

import { type MountedInvoice, redNotices, said } from './mount-invoice';

const blocking = (m: MountedInvoice): ActionNotice[] => m.notices().filter((notice) => notice.id === 'base.blocking');

function expectNothingInvoiceableSaidOnce(m: MountedInvoice): ActionNotice {
  expect(said(m.wrapper.text(), 'Todavía no puedes facturar')).toBe(0);
  expect(redNotices(m)).toBe(0);
  const notices = blocking(m);
  expect(notices.map((notice) => notice.title)).toEqual(['Todavía no puedes facturar']);
  expect(notices[0].body).toContain('Los datos de tu negocio');
  return notices[0];
}

/** The notice offers one «Configurar» to the issuer's step: returns that action. */
export function expectIssuerToSetUp(m: MountedInvoice): NoticeAction {
  const notice = expectNothingInvoiceableSaidOnce(m);
  expect(notice.action).toEqual({ label: 'Configurar los datos del negocio', to: '/invoice/issuer' });
  expect(notice.secondary).toBeUndefined();
  return notice.action!;
}

/** The notice says that an administrator has to set the issuer up, and offers no «Configurar». */
export function expectAnAdministratorToSetUpTheIssuer(m: MountedInvoice): void {
  const notice = expectNothingInvoiceableSaidOnce(m);
  expect(said(notice.body ?? '', 'Esto lo tiene que configurar un administrador.')).toBe(1);
  expect([notice.action, notice.secondary]).toEqual([undefined, undefined]);
}

export function expectIssuerSaidNoMore(m: MountedInvoice): void {
  expect(said(m.wrapper.text(), 'Todavía no puedes facturar')).toBe(0);
  expect(redNotices(m)).toBe(0);
  expect(blocking(m)).toEqual([]);
}
