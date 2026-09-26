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
import { describe, expect, it, vi } from 'vitest';

import { bootAppointmentNotices, onAppointmentEvent } from './appointment-notice';
import { CLIENT_INSTANCE } from './client-instance';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const ROW = {
  id: 'apt-1',
  customer_name: 'Laura Gómez',
  service_name: 'Corte y peinado',
  staff_name: 'Ana',
  start_date_label: 'martes, 30 de septiembre de 2026',
  start_time_label: '10:30',
  status: 'pending',
};

/** Renders the key and its params, so the tests pin WHICH sentence, not its prose. */
const t = (key: string, params?: Record<string, unknown>) => (params ? `${key}${JSON.stringify(params)}` : key);

function fakeClient(get: () => Promise<unknown> = async () => [ROW]) {
  const handlers = new Map<string, (payload: unknown, meta: { clientInstance?: string }) => void>();
  const off = vi.fn();
  const client = {
    query: vi.fn(async (name: string) => {
      if (name === 'appointments.appointments.get') return get();
      return [];
    }),
    onEvent: vi.fn((name: string, handler: (payload: unknown, meta: { clientInstance?: string }) => void) => {
      handlers.set(name, handler);
      return off;
    }),
  };
  return { client: client as never, raw: client, handlers, off };
}

describe('a booking that did not come from a till', () => {
  it('gives a system notice with the customer, the service, the day and hour and who does it', async () => {
    const { client, raw } = fakeClient();
    const notify = vi.fn(async (_title: string, _body: string) => {});

    await onAppointmentEvent(client, 'created', { appointment_id: 'apt-1' }, {}, { notify, t });

    expect(raw.query).toHaveBeenCalledWith('appointments.appointments.get', { appointment_id: 'apt-1' });
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith(
      'appointmentNotice.createdFor{"customer":"Laura Gómez"}',
      'Corte y peinado · appointmentNotice.when{"date":"martes, 30 de septiembre de 2026","time":"10:30"} · Ana',
    );
  });

  it('reads the id under its old name too (`new_id`)', async () => {
    const { client, raw } = fakeClient();
    await onAppointmentEvent(client, 'created', { new_id: 'apt-1' }, {}, { notify: async () => {}, t });
    expect(raw.query).toHaveBeenCalledWith('appointments.appointments.get', { appointment_id: 'apt-1' });
  });

  it('when the appointment cannot be read, still warns with what the event says', async () => {
    const { client } = fakeClient(async () => {
      throw new Error('forbidden');
    });
    const notify = vi.fn(async (_title: string, _body: string) => {});

    await onAppointmentEvent(
      client,
      'created',
      { appointment_id: 'apt-1', customer_name: 'Laura Gómez', service_name: 'Corte y peinado', staff_name: 'Ana' },
      {},
      { notify, t },
    );

    expect(notify).toHaveBeenCalledWith(
      'appointmentNotice.createdFor{"customer":"Laura Gómez"}',
      'Corte y peinado · Ana',
    );
  });

  it('without a customer name, the title does not leave a hole', async () => {
    const { client } = fakeClient(async () => [{ ...ROW, customer_name: '' }]);
    const notify = vi.fn(async (_title: string, _body: string) => {});
    await onAppointmentEvent(client, 'created', { appointment_id: 'apt-1' }, {}, { notify, t });
    expect(notify.mock.calls[0][0]).toBe('appointmentNotice.created');
  });
});

describe('the day and the hour', () => {
  it('are said only together — a lone date or a lone hour is left out', async () => {
    const { client } = fakeClient(async () => [{ ...ROW, start_time_label: '' }]);
    const notify = vi.fn(async (_title: string, _body: string) => {});
    await onAppointmentEvent(client, 'created', { appointment_id: 'apt-1' }, {}, { notify, t });
    expect(notify.mock.calls[0][1]).toBe('Corte y peinado · Ana');
  });
});

describe('a booking typed in at a till', () => {
  it('is not announced on the till that made it', async () => {
    const { client } = fakeClient();
    const notify = vi.fn(async (_title: string, _body: string) => {});
    await onAppointmentEvent(
      client,
      'created',
      { appointment_id: 'apt-1' },
      { clientInstance: CLIENT_INSTANCE },
      { notify, t },
    );
    expect(notify).not.toHaveBeenCalled();
  });

  it('nor on the other till of the same counter', async () => {
    const { client } = fakeClient();
    const notify = vi.fn(async (_title: string, _body: string) => {});
    await onAppointmentEvent(
      client,
      'created',
      { appointment_id: 'apt-1' },
      { clientInstance: 'another-tab' },
      { notify, t },
    );
    expect(notify).not.toHaveBeenCalled();
  });
});

describe('a cancellation', () => {
  it('by the customer (not from a till) gives a notice naming who cancelled and when it was', async () => {
    const { client } = fakeClient(async () => [{ ...ROW, status: 'cancelled' }]);
    const notify = vi.fn(async (_title: string, _body: string) => {});

    await onAppointmentEvent(
      client,
      'cancelled',
      { appointment_id: 'apt-1', reason: 'no puedo', channel: 'customer' },
      {},
      { notify, t },
    );

    expect(notify).toHaveBeenCalledWith(
      'appointmentNotice.cancelledFor{"customer":"Laura Gómez"}',
      'Corte y peinado · appointmentNotice.when{"date":"martes, 30 de septiembre de 2026","time":"10:30"} · Ana',
    );
  });

  it('made at a till is not announced', async () => {
    const { client } = fakeClient();
    const notify = vi.fn(async (_title: string, _body: string) => {});
    await onAppointmentEvent(client, 'cancelled', { appointment_id: 'apt-1' }, { clientInstance: 'x' }, { notify, t });
    expect(notify).not.toHaveBeenCalled();
  });

  it('whose appointment cannot be read still warns, without a name', async () => {
    const { client } = fakeClient(async () => []);
    const notify = vi.fn(async (_title: string, _body: string) => {});
    await onAppointmentEvent(client, 'cancelled', { appointment_id: 'apt-1' }, {}, { notify, t });
    expect(notify).toHaveBeenCalledWith('appointmentNotice.cancelled', '');
  });
});

describe('what never happens', () => {
  it('an event without an appointment id asks nothing and warns of nothing', async () => {
    const { client, raw } = fakeClient();
    const notify = vi.fn(async (_title: string, _body: string) => {});
    await onAppointmentEvent(client, 'created', {}, {}, { notify, t });
    await onAppointmentEvent(client, 'cancelled', null, {}, { notify, t });
    expect(raw.query).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
  });

  it('a failing notice does not escape the listener', async () => {
    const { client } = fakeClient();
    const notify = vi.fn(async () => {
      throw new Error('denied');
    });
    await expect(
      onAppointmentEvent(client, 'created', { appointment_id: 'apt-1' }, {}, { notify, t }),
    ).resolves.toBeUndefined();
  });
});

describe('the boot', () => {
  it('listens to the booking and the cancellation, and cancels both', async () => {
    const { client, raw, handlers, off } = fakeClient();
    const notify = vi.fn(async (_title: string, _body: string) => {});

    const stop = bootAppointmentNotices(client, { notify, t });

    expect([...handlers.keys()].sort()).toEqual([
      'appointments.appointment.cancelled',
      'appointments.appointment.created',
    ]);
    handlers.get('appointments.appointment.created')?.({ appointment_id: 'apt-1' }, {});
    await vi.waitFor(() => expect(notify).toHaveBeenCalledTimes(1));
    expect(raw.onEvent).toHaveBeenCalledTimes(2);

    stop();
    expect(off).toHaveBeenCalledTimes(2);
  });
});

describe('the words (en + es)', () => {
  type Catalogue = { appointmentNotice: Record<string, string> };
  const KEYS = ['created', 'createdFor', 'cancelled', 'cancelledFor', 'when'] as const;

  it.each(KEYS)('«%s» exists in English and in Spanish', (key) => {
    expect((en as unknown as Catalogue).appointmentNotice?.[key]).toBeTruthy();
    expect((es as unknown as Catalogue).appointmentNotice?.[key]).toBeTruthy();
  });
});
