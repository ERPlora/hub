// The agenda's list of the bookings to confirm (apps/appointment/queries/appointments.py), written by hand as
// `operations.d.ts`: every booking still pending and not started, of any day, soonest first.
import type { AppointmentPage } from './operations';

declare module '@erplora/ui/sdk' {
  interface Operations {
    'appointment.appointment.list_to_confirm': { input: { limit?: number; offset?: number }; output: AppointmentPage };
  }
}
