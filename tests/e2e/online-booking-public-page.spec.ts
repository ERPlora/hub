// flow: ONLINE_BOOKING-F01 ONLINE_BOOKING-F10 ONLINE_BOOKING-F11
// The booking page a customer opens without a session at `/p/<slug>/book` of the business's own host, in each of the
// three sizes (apps/online_booking/WORKBOOK.md), with a Spanish browser: it says it is loading, books a service with no
// preference of professional on a day and at a free time with her name and mobile (the appointment is in the diary,
// pending, booked online), sees and cancels it right away on the same page, says when the business has nothing to book
// online and when it does not take online bookings, with no menu of the team's, all under the strict CSP of every page
// (no violation reported). Another business's slug on this host is not found, nor this one's on another host. The
// owner makes the cast through each app's API; everything is named «E2E PB …» and removed before and after, and the
// settings of the page and of Appointments put back. One screenshot per state and size
// (`online-booking-public-<state>-<width>`).
import { type Browser, expect, type Page, test } from '@playwright/test';

import { aMonday } from './appointment-helpers';
import { A, B, capture, psql } from './helpers';
import { cast, keepTheBusiness } from './online-booking-helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, ownerPage, post } from './service-helpers';

const TAG = 'E2E PB';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;
/** A Spanish mobile unique to the run and to the size (`6` + eight digits). */
const mobile = (n: number): string => `6${String(Date.now() + n * 7919).slice(-8)}`;
const PAGE = `${A}/p/a/book`;

keepTheBusiness(TAG);

/** A visitor without a session, in Spanish, at `viewport`; every CSP violation the page reports is kept. */
async function visitor(browser: Browser, viewport: { width: number; height: number }, address: string) {
  const context = await browser.newContext({ viewport, locale: 'es-ES', extraHTTPHeaders: { 'X-Forwarded-For': address } });
  const page = await context.newPage();
  const violations: string[] = [];
  page.on('console', (message) => {
    if (/Content Security Policy|Trusted Type/i.test(message.text())) violations.push(message.text());
  });
  return { context, page, violations };
}

const flow = (page: Page) => page.locator('[data-testid=ob-preview]');

FLOW_VIEWPORTS.forEach((vp, index) => {
  test(`a customer books on the business's page without a session at ${vp.label}`, async ({ browser }) => {
    const { context: owner } = await ownerPage(browser, '/online_booking/bookings', vp);
    const { context, page, violations } = await visitor(browser, vp, `10.${index + 1}.${Math.floor(Math.random() * 250)}.1`);
    const shoot = (state: string) => capture(page, `online-booking-public-${state}-${vp.label}`);
    const day = aMonday(index);
    try {
      const who = await cast(owner, named(vp.label), day);
      await post(owner, '/online_booking/settings', {
        page_title: named(`Salon ${vp.label}`),
        welcome_message: 'Tu próxima cita, sin llamar.',
        logo_url: `${A}/static/base/img/logo.png`,
        primary_color: '#6366f1',
      }, 200);

      // Loading: the page holds its business's answer (then every call goes through).
      let release: () => void = () => {};
      const held = new Promise<void>((resolve) => (release = resolve));
      await page.route('**/p/a/api/online_booking.public.page', async (route) => {
        await held;
        await route.continue();
      });
      await page.goto(PAGE);
      await expect(flow(page)).toContainText('Cargando la página…');
      await shoot('loading');
      release();

      // Booking: the service, no preference, the day and a free time, name and mobile; pending, in the diary.
      await expect(page.locator('[data-testid=ob-preview-title]')).toHaveText(named(`Salon ${vp.label}`));
      await expect(flow(page)).toContainText('Reserva online');
      await expect(page.locator('[data-testid=ob-preview-business-logo]')).toBeVisible();
      await expect.poll(() => page.locator('[data-testid=ob-preview-business-logo]').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
      await expect(page.locator('[data-testid=ob-preview-privacy]')).toContainText('usará tus datos para gestionar esta reserva');
      await expect(page.locator('[data-testid=ob-preview-privacy] a')).toHaveAttribute('href', /\/legal\/privacy\/$/);
      const trap = page.locator('[data-testid=ob-preview-trap]');
      await expect(trap).toBeHidden();
      await expect(trap).toHaveAttribute('aria-hidden', 'true');
      await expect(page.locator('[data-testid=ob-preview-trap-input]')).toHaveAttribute('tabindex', '-1');
      await expect(page.locator('[data-testid=ob-preview-trap-input]')).toHaveAttribute('autocomplete', 'off');
      await shoot('form');
      // A customer is no member of the team: no side menu, and no button to open one.
      await expect(page.locator('ion-menu-button')).toBeHidden();
      await page.locator(`[data-testid=ob-preview-service-${who.service.id}]`).click();
      const dayInput = page.locator('[data-testid=ob-preview-day] input');
      await dayInput.fill(day);
      await dayInput.press('Tab');
      await page.locator('[data-testid="ob-preview-time-10:00"]').click();
      const marta = named(`Marta ${vp.label}`);
      await page.locator('[data-testid=ob-preview-name] input').fill(marta);
      await page.locator('[data-testid=ob-preview-phone] input').fill(mobile(index));
      await page.locator('[data-testid=ob-preview-book]').click();
      const booked = page.locator('[data-testid=ob-preview-booked]');
      await expect(booked).toContainText('Reserva APT-');
      await expect(booked).toContainText('Hemos recibido tu reserva. El negocio la confirmará en breve.');
      await noHorizontalScroll(page, `the booked page at ${vp.label}`);
      const number = ((await booked.textContent()) ?? '').match(/APT-\d{8}-\d{4}/)![0];
      const appointment = psql(
        `select status || ' ' || source || ' ' || staff_id || ' ' || created_by from appointment_appointment where number = '${number}'`,
      );
      expect(appointment).toBe(`pending online ${who.member.id} online booking`);
      await shoot('booked');

      // Right after booking she sees it and cancels it, as the customer: «the customer asked» in the diary.
      await page.locator('[data-testid=ob-preview-view]').click();
      const status = page.locator('[data-testid=ob-preview-status]');
      await expect(status).toContainText('Pendiente');
      await page.locator('[data-testid=ob-preview-cancel]').click();
      await expect(status).toContainText('Cancelada');
      expect(psql(`select status || ' ' || cancelled_by_customer from appointment_appointment where number = '${number}'`)).toBe('cancelled true');
      await noHorizontalScroll(page, `the cancelled booking at ${vp.label}`);

      // Empty: nothing of the business is booked online.
      const online = psql(`select string_agg(quote_literal(id::text), ',') from service_service where allow_online_booking`);
      expect(online, 'the cast books online').toContain(who.service.id);
      try {
        psql(`update service_service set allow_online_booking = false where id in (${online})`);
        await page.goto(PAGE);
        await expect(page.locator('[data-testid=ob-preview-no-services]')).toHaveText('Este negocio no tiene nada para reservar online ahora mismo.');
        await expect(page.locator('[data-testid=ob-preview-name]')).toHaveCount(0);
        await expect(page.locator('[data-testid=ob-preview-phone]')).toHaveCount(0);
        await expect(page.locator('[data-testid=ob-preview-book]')).toHaveCount(0);
        await shoot('empty');
      } finally {
        psql(`update service_service set allow_online_booking = true where id in (${online})`);
      }

      // Error: the business stops taking online bookings.
      await post(owner, '/online_booking/settings', { is_enabled: false }, 200);
      await page.goto(PAGE);
      await expect(page.locator('[data-testid=ob-preview-error]')).toContainText('Este negocio no acepta reservas online ahora mismo.');
      await noHorizontalScroll(page, `the closed page at ${vp.label}`);
      await shoot('error');

      // Another business's slug on this host, and this one's on another host: not found.
      expect((await context.request.get(`${A}/p/b/book`)).status()).toBe(404);
      expect((await context.request.get(`${B}/p/a/book`)).status()).toBe(404);
      expect(violations, 'CSP violations on the public page').toEqual([]);
    } finally {
      await context.close();
      await owner.close();
    }
  });
});
