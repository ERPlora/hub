// Online booking → Settings (WORKBOOK «Ajustes»; ONLINE_BOOKING-F07): only for whoever may save them. The
// public page's fields and the diary's booking rules come live (`online_booking.settings.get`); «Save» sends
// only what the person touched and changed, all of it in one write, and says «Settings saved.»; a refusal
// goes under its field. Below, the services offered with their «Online booking» switch, saved at once in
// Services (`service.service.update`).
import { describe, expect, it } from 'vitest';

import type { SettingsOut } from '../operations';
import { pressEnter } from '../../../../base/frontend/__tests__/settings-form';
import { click, errorFrame, flush, ionChecked, ionValue, MANAGER, type MountOptions, mountOnlineBooking, page, settle } from '../__tests__/mount-online-booking';
import SettingsPage from './SettingsPage.vue';

const OP = 'online_booking.settings.get';
const SERVICES = 'service.service.list';
const SETTINGS: SettingsOut = {
  is_enabled: false,
  page_title: '',
  welcome_message: '',
  primary_color: '#6366f1',
  logo: '',
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

type SettingsScreen = Awaited<ReturnType<typeof setup>>;

const LOGO = { id: '0123456789abcdef.png', url: '/p/media/hub/online_booking/logo/0123456789abcdef.png' };
const OLD_LOGO = { id: 'fedcba0987654321.png', url: '/p/media/hub/online_booking/logo/fedcba0987654321.png' };

async function chooseLogo(s: SettingsScreen, file: File): Promise<void> {
  const input = s.field('logo-file') as HTMLInputElement | null;
  if (!input) throw new Error('The logo file input is missing');
  let value = `C:\\fakepath\\${file.name}`;
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  Object.defineProperty(input, 'value', { get: () => value, set: (next: string) => (value = next), configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await settle();
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
    expect(s.field('logo_url') === null).toBe(true);
    expect(s.field('logo-label')?.textContent).toBe('Logo');
    expect(s.field('logo-empty') !== null).toBe(true);
    expect(s.field('save').disabled).toBe(true);
  });

  it('uploads a chosen logo, shows its preview and saves its id', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answerBy({
      '/api/online_booking/settings/logo': [201, LOGO],
      '/api/online_booking/settings': [200, { ...SETTINGS, logo: LOGO.id, logo_url: LOGO.url }],
    });
    await chooseLogo(s, new File([new Uint8Array([1, 2, 3])], 'logo.png', { type: 'image/png' }));
    expect(s.sent()[0]).toEqual({
      method: 'POST',
      path: '/api/online_booking/settings/logo',
      query: {},
      body: { filename: 'logo.png', content_type: 'image/png', data_base64: 'AQID' },
    });
    expect(s.field('logo-image').getAttribute('src')).toBe(LOGO.url);
    await click(s.field('save'));
    expect(s.sent().at(-1)?.body).toEqual({ logo: LOGO.id });
  });

  it('removes the current logo from the preview and saves an empty logo', async () => {
    const s = await setup();
    await s.show({ ...SETTINGS, logo: OLD_LOGO.id, logo_url: OLD_LOGO.url });
    expect(s.field('logo-image').getAttribute('src')).toBe(OLD_LOGO.url);
    s.answer(200, SETTINGS);
    await click(s.field('logo-remove'));
    expect(s.field('logo-image') === null).toBe(true);
    expect(s.field('logo-empty') !== null).toBe(true);
    await click(s.field('save'));
    expect(s.sent().at(-1)?.body).toEqual({ logo: '' });
  });

  it('shows the server reason when it rejects the chosen logo', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(SETTINGS);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Este archivo no es una imagen PNG.', fields: { data_base64: 'Este archivo no es una imagen PNG.' } } });
    await chooseLogo(s, new File(['not a png'], 'logo.png', { type: 'image/png' }));
    expect(s.field('logo-error')?.textContent).toContain('Este archivo no es una imagen PNG.');
    expect(s.sent()).toHaveLength(1);
    expect(s.field('logo-empty') !== null).toBe(true);
  });

  it('puts a refused logo under Logo until another one is chosen', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    const reason = 'That logo was not uploaded to this business: upload it again.';
    s.answerBy({ '/api/online_booking/settings/logo': [201, LOGO] });
    await chooseLogo(s, new File([new Uint8Array([1, 2, 3])], 'logo.png', { type: 'image/png' }));
    s.answer(422, { error: { code: 'invalid_payload', message: reason, fields: { logo: reason } } });
    await click(s.field('save'));
    expect(s.field('logo-save-error')?.textContent).toContain(reason);
    s.answerBy({ '/api/online_booking/settings/logo': [201, OLD_LOGO] });
    await chooseLogo(s, new File([new Uint8Array([4, 5, 6])], 'other.png', { type: 'image/png' }));
    expect(s.field('logo-save-error')).toBeNull();
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
    // Enter in a field submits the form (Ionic puts a hidden submit button in it): the same save as «Save».
    await ionValue(s.field('slot_interval'), '30', 'ionInput');
    await pressEnter(s.inDoc('ob-settings'));
    expect(s.sent().at(-1)?.body).toEqual({ slot_interval: 30 });
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
    expect(s.field('save-error')?.textContent).toContain('Invalid payload');
  });

  describe('a refusal by fields (hub#854, as FormModal and the Services settings do: hub#821)', () => {
    const REFUSAL = {
      error: {
        code: 'invalid_payload',
        message: 'Invalid payload',
        fields: {
          primary_color: 'Write the colour as #RRGGBB (for example #6366f1).',
          min_booking_notice: 'Ensure this value is less than or equal to 10080.',
        },
      },
    };

    /** Saves a colour that is no colour and a notice of a year, and the server refuses both fields. */
    async function refused() {
      const s = await setup();
      await s.show(SETTINGS);
      s.answer(422, REFUSAL);
      await ionValue(s.field('primary_color'), 'blue', 'ionInput');
      await ionValue(s.field('min_booking_notice'), '525600', 'ionInput');
      await click(s.field('save'));
      /** Whether the red notice is on screen. */
      const notice = () => s.field('save-error') !== null;
      const says = (name: string) => s.field(name).errorText ?? '';
      const marked = (name: string) => s.field(name).classList.contains('ion-invalid');
      return { ...s, notice, says, marked };
    }

    it('the notice goes as soon as something is changed, and a field’s message as soon as that field is', async () => {
      const s = await refused();
      expect(s.notice()).toBe(true);
      expect([s.says('primary_color'), s.says('min_booking_notice')]).toEqual([
        'Write the colour as #RRGGBB (for example #6366f1).',
        'Ensure this value is less than or equal to 10080.',
      ]);
      await ionValue(s.field('primary_color'), '#112233', 'ionInput');
      expect(s.notice()).toBe(false);
      expect([s.says('primary_color'), s.marked('primary_color')]).toEqual(['', false]);
      expect([s.says('min_booking_notice'), s.marked('min_booking_notice')]).toEqual(['Ensure this value is less than or equal to 10080.', true]);
    });
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
