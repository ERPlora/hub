// The switch of how the bookings by WhatsApp confirm (WHATSAPP_INBOX-F16), under a card that is on: «Appointments
// confirm by themselves» or «I review them first» writes Citas' rule (`auto_confirm_online`), «Reservations confirm by
// themselves» Reservas' (`auto_confirm`), at once; with «I review them first» it says where they wait. A failed save says
// so and goes back to how it was. Each choice is a full-width row whose words wrap: never cut on a phone
// (whatsapp_inbox#285).
import { describe, expect, it } from 'vitest';

import { ADMIN, ionValue, type MountOptions, mountInbox, settle } from '../__tests__/mount-inbox';
import AutoReplyRule from './AutoReplyRule.vue';

type Answer = { status?: number; body?: unknown };

function api(answers: Answer[] = []) {
  return () => {
    const next = answers.shift() ?? {};
    return Response.json(next.body ?? {}, { status: next.status ?? 200 });
  };
}

async function mount(which: 'appointments' | 'tables', options: MountOptions = {}) {
  const page = await mountInbox(AutoReplyRule, { session: ADMIN, props: { which }, ...options });
  await page.live();
  return page;
}

// The choices' words, read from each `ion-radio`: the test DOM does not reach them through their parents' text.
const choices = (choice: ReturnType<Awaited<ReturnType<typeof mount>>['find']>) =>
  choice.findAll('ion-radio').map((radio) => radio.element.textContent?.trim() ?? '');

const posted = (page: Awaited<ReturnType<typeof mount>>) =>
  page.sent().filter((call) => call.method === 'POST').map((call) => `${call.path} ${JSON.stringify(call.body)}`);

describe('AutoReplyRule', () => {
  it('shows the rule of Citas and saves the other choice at once', async () => {
    const page = await mount('appointments', { api: api() });
    await page.result('appointment.settings.get', { auto_confirm_online: true });
    const choice = page.find('whatsapp-inbox-autoreply-appointments-confirm');
    expect(choices(choice)).toContain('Appointments confirm by themselves');
    expect(choices(choice)).toContain('I review them first');
    expect(page.find('whatsapp-inbox-autoreply-appointments-review').exists()).toBe(false);
    await ionValue(choice.find('ion-radio-group').element, 'review');
    expect(posted(page)).toEqual(['/api/appointment/settings {"auto_confirm_online":false}']);
    expect(page.find('whatsapp-inbox-autoreply-appointments-review').text()).toBe(
      'Each new appointment waits for you in the Diary with “Confirm”.',
    );
  });

  it("writes Reservas' rule for the tables, in Spanish", async () => {
    const page = await mount('tables', { api: api(), locale: 'es' });
    await page.result('reservation.settings.get', { auto_confirm: false });
    const choice = page.find('whatsapp-inbox-autoreply-tables-confirm');
    expect(choices(choice)).toContain('Las reservas se confirman solas');
    expect(page.find('whatsapp-inbox-autoreply-tables-review').text()).toBe(
      'Cada reserva nueva te espera en Reservas con “Confirmar”.',
    );
    await ionValue(choice.find('ion-radio-group').element, 'auto');
    expect(posted(page)).toEqual(['/api/reservation/settings {"auto_confirm":true}']);
  });

  it('says it could not save and goes back to how it was', async () => {
    const failing = api([{ status: 500, body: { error: { code: 'internal_error', message: 'x' } } }]);
    const page = await mount('tables', { api: failing });
    await page.result('reservation.settings.get', { auto_confirm: false });
    const group = page.find('whatsapp-inbox-autoreply-tables-confirm').find('ion-radio-group');
    await ionValue(group.element, 'auto');
    await settle();
    expect(page.find('whatsapp-inbox-autoreply-tables-confirm-error').text()).toBe(
      'Could not save how reservations confirm. Try again.',
    );
    expect((group.element as HTMLElement & { value?: string }).value).toBe('review');
  });

  it('says it is loading before the rule comes', async () => {
    const page = await mount('appointments');
    expect(page.find('whatsapp-inbox-autoreply-appointments-confirm-loading').exists()).toBe(true);
  });
});
