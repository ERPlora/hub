// Online booking → Settings (WORKBOOK «Ajustes»; ONLINE_BOOKING-F07): only for whoever may save them. The
// public page's fields and the diary's booking rules come live (`online_booking.settings.get`); «Save» sends
// only what the person touched and changed, all of it in one write, and says «Settings saved.»; a refusal
// goes under its field. Below, the services offered with their «Online booking» switch, saved at once in
// Services (`service.service.update`).
import { describe, expect, it } from 'vitest';

import type { SettingsOut } from '../operations';
import { click, errorFrame, flush, ionChecked, ionValue, MANAGER, type MountOptions, mountOnlineBooking, page, settle } from '../__tests__/mount-online-booking';
import SettingsPage from './SettingsPage.vue';

const OP = 'online_booking.settings.get';
const SERVICES = 'service.service.list';
const SETTINGS: SettingsOut = {
  is_enabled: false,
  page_title: '',
  welcome_message: '',
  primary_color: '#6366f1',
  logo_url: '',
  require_email: false,
  max_upcoming_per_customer: 3,
  allow_staff_selection: true,
  allow_notes: true,
  confirmation_message: '',
  cancellation_policy: '',
  min_booking_notice: 60,
  max_advance_booking: 90,
  slot_interval: 15,
  auto_confirm_online: true,
  allow_customer_cancellation: true,
  cancellation_notice_hours: 24,
  timezone: 'Europe/Madrid',
};
const service = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id,
  name,
  is_bookable: true,
  allow_online_booking: true,
  ...over,
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; disabled?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountOnlineBooking(SettingsPage, { path: '/online_booking/settings', ...options });
  await m.live();
  const field = (name: string) => m.inDoc(`ob-settings-${name}`) as Control;
  return { ...m, field, show: (data: unknown) => m.result(OP, data) };
}

describe('SettingsPage', () => {
  it('paints the page settings and the booking rules with their labels', async () => {
    const s = await setup();
    expect(s.field('loading')?.textContent).toContain('Loading settings…');
    await s.show(SETTINGS);
    expect(s.find('ob-settings').text()).toContain('Booking page settings');
    expect([s.field('page_title').label, s.field('primary_color').label, s.field('min_booking_notice').label]).toEqual([
      'Page title',
      'Primary colour',
      'Minimum booking notice (minutes)',
    ]);
    expect([s.field('primary_color').value, s.field('slot_interval').value, s.field('is_enabled').checked]).toEqual(['#6366f1', '15', false]);
    expect(s.field('auto_confirm_online').textContent).toBe("Confirm the customer's bookings automatically");
    expect(s.field('save').disabled).toBe(true);
  });

  it('saves only what was touched and changed, the page and the rules together, and says so', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await ionChecked(s.field('is_enabled'), true);
    await ionValue(s.field('page_title'), 'Salón Lucía', 'ionInput');
    await ionValue(s.field('min_booking_notice'), '120', 'ionInput');
    await ionValue(s.field('slot_interval'), '15', 'ionInput');
    s.answer(200, { ...SETTINGS, is_enabled: true, page_title: 'Salón Lucía', min_booking_notice: 120 });
    await click(s.field('save'));
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/online_booking/settings',
        query: {},
        body: { is_enabled: true, page_title: 'Salón Lucía', min_booking_notice: 120 },
      },
    ]);
    await settle();
    expect(s.field('saved')?.textContent).toContain('Settings saved.');
  });

  it('puts a refusal under its field, keeping what was typed', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await ionValue(s.field('primary_color'), 'blue', 'ionInput');
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { primary_color: 'Write the colour as #RRGGBB (for example #6366f1).' } } });
    await click(s.field('save'));
    expect(s.field('primary_color').errorText).toBe('Write the colour as #RRGGBB (for example #6366f1).');
    expect(s.field('primary_color').value).toBe('blue');
    expect(s.field('save-error')?.textContent).toContain('Could not save');
  });

  it('lists the services with their online booking switch, saved at once in Services', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    expect(s.params(SERVICES)).toEqual([{ limit: 100 }]);
    await s.result(SERVICES, page([service('v1', 'Haircut'), service('v2', 'Consultation', { is_bookable: false, allow_online_booking: false })], 2, 100));
    expect(s.field('service-v1').checked).toBe(true);
    expect(s.field('service-v2').textContent).toContain('Consultation');
    expect(s.find('ob-settings-services').text()).toContain('Not bookable in the diary');
    s.answer(200, { ...service('v1', 'Haircut'), allow_online_booking: false });
    await ionChecked(s.field('service-v1'), false);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/service/services/update', query: {}, body: { id: 'v1', allow_online_booking: false } }]);
  });

  it('says why a service could not be changed, and when there are none', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await s.result(SERVICES, page([service('v1', 'Haircut')], 140, 100));
    expect(s.find('ob-settings-services-more').text()).toBe('Showing 1 of 140: search to find the others.');
    s.answer(403, { error: { code: 'permission_denied', message: 'Permission “service.change_service” is required.' } });
    await ionChecked(s.field('service-v1'), false);
    expect(s.field('services-error')?.textContent).toContain('The service could not be changed');
    const empty = await setup();
    await empty.show(SETTINGS);
    await empty.result(SERVICES, page([], 0, 100));
    expect(empty.find('ob-settings-services-empty').text()).toBe('No services yet. Add them in Services.');
  });

  it('a failed load says so, with no endless «Loading…» next to it', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.field('load-error')?.textContent).toContain('The settings could not be loaded');
    expect(s.field('loading')).toBeNull();
  });

  it('a service switch that could not be saved goes back to what it was', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    await s.result(SERVICES, page([service('v1', 'Haircut')], 1, 100));
    s.answer(403, { error: { code: 'permission_denied', message: 'Permission “service.change_service” is required.' } });
    await ionChecked(s.field('service-v1'), false);
    expect(s.field('services-error')?.textContent).toContain('The service could not be changed');
    expect(s.field('service-v1').checked).toBe(true);
  });

  it('is closed to who may not change them', async () => {
    const s = await setup({ session: MANAGER });
    expect(s.field('forbidden')?.textContent).toContain('You do not have permission');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(SETTINGS);
    expect(s.find('ob-settings').text()).toContain('Configuración de la página de reservas');
    expect(s.field('is_enabled').textContent).toBe('Página pública activada');
    expect(s.field('save').textContent?.trim()).toBe('Guardar');
  });
});
