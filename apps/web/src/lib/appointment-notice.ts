// hub#2168 — **a salon's till heard nothing when a customer booked or cancelled.**
//
// A booking made over WhatsApp, the web or a flow, and a cancellation by the customer, only showed
// up if somebody happened to be looking at the agenda. Square Appointments, Fresha and Booksy warn
// the business's device of every new booking and every cancellation; the shell already did it for
// a kitchen order (`print-comanda.ts`), so this is its twin for appointments.
//
// What is pinned: the notice is for what did NOT come from a till (the frame carries the tab that
// sent the command, hub#1980 — nobody needs to be told about the booking they just typed in), its
// words come from the catalogue by key (ADR-0055) with the day and hour the appointment itself
// resolves in the business's clock (appointments#151), and a failure never escapes the listener.
import type { ErploraClient, EventMeta } from '@erplora/module-sdk';

export type AppointmentNoticeKind = 'created' | 'cancelled';

/**
 * The module whose bookings this file announces. The bell's notice (hub#2303) leaves its counters
 * out: its `to_confirm` goes up with the same booking that already rang here.
 */
export const APPOINTMENT_NOTICE_MODULE = 'appointments';

export interface AppointmentNoticeDeps {
  /** Notification of the SYSTEM, the same door as the kitchen order's (`peripherals.notify`). */
  notify: (title: string, body: string) => Promise<void>;
  /** The caller owns i18n (ADR-0055): this file only picks the key and its params. */
  t: (key: string, params?: Record<string, unknown>) => string;
}

/** Starts both listeners at shell boot. Returns the function that stops them. */
export function bootAppointmentNotices(client: ErploraClient, deps: AppointmentNoticeDeps): () => void {
  const offCreated = client.onEvent('appointments.appointment.created', (payload, meta) => {
    void onAppointmentEvent(client, 'created', payload, meta, deps).catch((e) =>
      console.warn('[appointment-notice]', e),
    );
  });
  const offCancelled = client.onEvent('appointments.appointment.cancelled', (payload, meta) => {
    void onAppointmentEvent(client, 'cancelled', payload, meta, deps).catch((e) =>
      console.warn('[appointment-notice]', e),
    );
  });
  return () => {
    offCreated();
    offCancelled();
  };
}

export async function onAppointmentEvent(
  client: ErploraClient,
  kind: AppointmentNoticeKind,
  payload: unknown,
  meta: EventMeta,
  deps: AppointmentNoticeDeps,
): Promise<void> {
  // hub#1980 stamps every frame with the tab whose command produced it. ANY value here — this
  // tab's own id or another till's — means a till made this booking or cancellation, and whoever
  // is standing at that counter already knows it. Nothing is queried: the notice only exists for
  // what did not come from a till at all (WhatsApp, the web, a flow, the customer themselves).
  if (meta?.clientInstance) return;

  const id = appointmentIdOf(payload);
  if (!id) return;

  // The row is the AUTHORITY when it can be read — appointments#151 resolves its day and hour in
  // the business's own timezone and in the caller's language, which the raw event payload cannot
  // do. A row that cannot be read (module gone, a stale id) falls back to the event's own fields:
  // still worth a notice, just a poorer one.
  const row = first(
    await client
      .query<Record<string, unknown>[]>('appointments.appointments.get', { appointment_id: id })
      .catch(() => undefined),
  );
  const source = row ?? (payload as Record<string, unknown>);

  const customer = str(source.customer_name).trim();
  const titleKey = kind === 'created' ? 'appointmentNotice.created' : 'appointmentNotice.cancelled';
  const title = customer ? deps.t(`${titleKey}For`, { customer }) : deps.t(titleKey);

  // Only when BOTH labels are there: a lone date or a lone hour reads as a typo, not as an answer.
  const dateLabel = str(source.start_date_label);
  const timeLabel = str(source.start_time_label);
  const when = dateLabel && timeLabel ? deps.t('appointmentNotice.when', { date: dateLabel, time: timeLabel }) : '';

  const body = [str(source.service_name).trim(), when, str(source.staff_name).trim()].filter(Boolean).join(' · ');

  // Best-effort, like the kitchen order's: a notice that cannot be shown must not break the
  // listener, and the booking or cancellation already happened either way.
  await deps.notify(title, body).catch(() => {});
}

function appointmentIdOf(payload: unknown): string | undefined {
  if (payload && typeof payload === 'object') {
    const p = payload as Record<string, unknown>;
    const id = p.appointment_id ?? p.new_id;
    return id != null ? String(id) : undefined;
  }
  return undefined;
}

function first<T>(v: T[] | T | undefined): T | undefined {
  return Array.isArray(v) ? v[0] : v;
}

function str(v: unknown): string {
  return v == null ? '' : String(v);
}
