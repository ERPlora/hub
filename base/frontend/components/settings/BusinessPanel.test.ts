// Settings › Business (BASE-G97, G98, G99; APP-BASE-6): the business as erplora.com registered it — its name, country,
// time zone (with the time it is there), currency and language — read-only, because erplora.com owns them: an owner or
// an administrator changes them there («Change on erplora.com», a new tab), the country never once the business is
// ready, the currency never (it is the country's). A demo has nothing to change. Below, «Fiscal data» opens Invoicing's
// issuer, or Apps while Invoicing is not on. Loading, and a reading that failed with «Retry», never a blank card.
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, OWNER, subId } from '../../__tests__/mount-base';
import type { Business } from '../../operations';
import BusinessPanel from './BusinessPanel.vue';

const BUSINESS: Business = {
  name: 'Peluquería Ana',
  country: 'ES',
  country_name: 'España',
  timezone: 'Atlantic/Canary',
  language: 'es',
  language_name: 'Español',
  currency: 'EUR',
  currency_label: 'EUR · Euro',
  currency_decimals: 2,
  demo: false,
  settings_url: 'https://erplora.com/businesses/0199/settings',
};

const withInvoice = (session: SessionMe, state: 'on' | 'off' = 'on'): SessionMe => ({
  ...session,
  apps: [{ label: 'invoice', state }],
  permissions: [...session.permissions, 'invoice.manage_issuer'],
});

async function panel(options: { session?: SessionMe; business?: Business | null; locale?: 'en' | 'es' } = {}) {
  const m = await mountBase(BusinessPanel, {
    session: options.session ?? withInvoice(OWNER),
    locale: options.locale ?? 'es',
    routes: ['/invoice/issuer', '/apps'],
  });
  const call = await m.live();
  if (options.business !== null) await m.result(call, 'base.business.get', options.business ?? BUSINESS);
  return { ...m, call };
}

type Wrapper = Awaited<ReturnType<typeof panel>>['wrapper'];
/** A part of a row (`value`, `title`, `hint`): Ionic's hydrated elements give happy-dom no text of their own. */
const part = (wrapper: Wrapper, row: string, which: 'value' | 'title' | 'hint') =>
  wrapper.get(`[data-testid="business-${row}"] [data-testid="settings-row-${which}"]`).text();
const value = (wrapper: Wrapper, row: string) => part(wrapper, row, 'value');
/** The «Change on erplora.com» link: an ion-button, whose href, target and rel are its properties. */
const changeLink = (wrapper: Wrapper) =>
  wrapper.get('[data-testid="business-change"]').element as HTMLElement & { href: string; target: string; rel: string };

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
  vi.setSystemTime(new Date('2026-10-24T09:30:00Z'));
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('BusinessPanel', () => {
  it('shows the business as erplora.com registered it, each value named in the person’s language', async () => {
    const m = await panel();
    expect(m.wrapper.get('h2').text()).toBe('Tu negocio');
    expect(value(m.wrapper, 'name')).toBe('Peluquería Ana');
    expect(value(m.wrapper, 'country')).toBe('España');
    expect(value(m.wrapper, 'currency')).toBe('EUR · Euro');
    expect(value(m.wrapper, 'language')).toBe('Español');
    // The zone with the time it is there now (Canary Islands: UTC+1 in October).
    expect(value(m.wrapper, 'timezone')).toBe('Atlantic/Canary · 10:30');
    expect(part(m.wrapper, 'language', 'title')).toBe('Idioma del negocio');
    expect(part(m.wrapper, 'language', 'hint')).toBe('El de quien no haya elegido el suyo');
    expect(part(m.wrapper, 'currency', 'hint')).toBe('La de su país, para precios y totales');
  });

  it('the time of the zone goes on by itself while the screen is open', async () => {
    const m = await panel();
    vi.advanceTimersByTime(30 * 60 * 1000);
    await flush();
    expect(value(m.wrapper, 'timezone')).toBe('Atlantic/Canary · 11:00');
  });

  it('a zone the browser does not know is shown as it is, without a time', async () => {
    const m = await panel({ business: { ...BUSINESS, timezone: 'Mars/Olympus' } });
    expect(value(m.wrapper, 'timezone')).toBe('Mars/Olympus');
  });

  it('an owner or an administrator changes them on erplora.com, in a new tab; nothing here is a field', async () => {
    const m = await panel();
    expect(m.wrapper.get('[data-testid="business-change-label"]').text()).toBe('Cambiar en erplora.com');
    const change = changeLink(m.wrapper);
    expect([change.href, change.target, change.rel]).toEqual([BUSINESS.settings_url, '_blank', 'noopener']);
    expect(m.wrapper.get('[data-testid="business-where"]').text()).toBe(
      'El nombre, la zona horaria y el idioma se cambian en erplora.com. El país no cambia una vez listo el negocio.',
    );
    expect(m.wrapper.findAll('ion-input, ion-select, input, select')).toHaveLength(0);
  });

  it('whoever does not run the hub reads them, and is told who changes them', async () => {
    const m = await panel({ session: EMPLOYEE });
    expect(m.wrapper.find('[data-testid="business-change"]').exists()).toBe(false);
    expect(m.wrapper.get('[data-testid="business-where"]').text()).toBe(
      'Solo el propietario o un administrador los cambian, en erplora.com.',
    );
  });

  it('a demo has no business on erplora.com: nothing to change, and a country it has not got reads «—»', async () => {
    const demo = { ...BUSINESS, name: '', country: '', country_name: '', demo: true, settings_url: '' };
    const m = await panel({ business: demo });
    expect(m.wrapper.find('[data-testid="business-change"]').exists()).toBe(false);
    expect(m.wrapper.get('[data-testid="business-where"]').text()).toBe(
      'Esta demo no tiene un negocio en erplora.com: sus datos no se cambian.',
    );
    expect(value(m.wrapper, 'name')).toBe('—');
    expect(value(m.wrapper, 'country')).toBe('—');
  });

  it('in English, the same rows with their English names', async () => {
    const m = await panel({ locale: 'en', business: { ...BUSINESS, country_name: 'Spain', language_name: 'Spanish' } });
    expect(m.wrapper.get('h2').text()).toBe('Your business');
    expect(part(m.wrapper, 'country', 'title')).toBe('Country');
    expect(value(m.wrapper, 'country')).toBe('Spain');
    expect(m.wrapper.get('[data-testid="business-change-label"]').text()).toBe('Change on erplora.com');
  });

  it('«Fiscal data» opens Invoicing’s issuer, where the invoices take it from', async () => {
    const m = await panel();
    expect(part(m.wrapper, 'fiscal', 'title')).toBe('Datos fiscales');
    expect(part(m.wrapper, 'fiscal', 'hint')).toBe('Razón social, NIF y domicilio: los que usan las facturas');
    await m.wrapper.get('[data-testid="business-fiscal"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/invoice/issuer');
  });

  it('without Invoicing on, «Fiscal data» says to install it and opens Apps', async () => {
    const m = await panel({ session: OWNER });
    expect(part(m.wrapper, 'fiscal', 'hint')).toBe('Instala la app Facturación para escribir los datos fiscales');
    await m.wrapper.get('[data-testid="business-fiscal"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/apps');
  });

  it('whoever may not write the issuer is not offered it', async () => {
    const m = await panel({ session: { ...EMPLOYEE, apps: [{ label: 'invoice', state: 'on' }] } });
    expect(m.wrapper.find('[data-testid="business-fiscal"]').exists()).toBe(false);
  });

  it('while it loads: «Loading the business’s data…», and no row painted empty', async () => {
    const m = await panel({ business: null });
    expect(m.wrapper.get('[data-testid="business-loading-text"]').text()).toBe('Cargando los datos del negocio…');
    expect(m.wrapper.find('[data-testid="business-name"]').exists()).toBe(false);
  });

  it('a reading that failed says so with «Retry», never a blank card', async () => {
    const m = await panel({ business: null });
    m.call.push(errorFrame(subId(m.client, 'base.business.get'), 'internal'));
    await flush();
    const failed = m.wrapper.get('[data-testid="business-error"]');
    expect(failed.text()).toContain('No se pudieron cargar los datos del negocio');
    expect(m.wrapper.find('[data-testid="business-retry"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="business-name"]').exists()).toBe(false);
  });
});
