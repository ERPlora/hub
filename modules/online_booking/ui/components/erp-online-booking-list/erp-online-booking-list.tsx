import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `online_booking` (Stencil). Mini-app: listado de reservas
// online + alta rápida + acciones de estado por fila (confirmar/cancelar/completar/
// no-show/borrar). Es una de las piezas que carga el shell vía ui.entry
// (modules/online_booking/dist/online_booking.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). La generación
// de referencia, validación de fecha futura, transiciones de estado y detección de
// doble reserva viven en runtime/WASM — ver WASM-TODO.md.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Booking {
  id: string;
  booking_reference: string;
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  service_name: string;
  staff_name: string;
  booking_date: string;
  booking_time: string;
  duration_minutes: number;
  status: string;
  booking_type: string;
  notes: string;
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente',
  confirmed: 'Confirmada',
  cancelled: 'Cancelada',
  completed: 'Completada',
  no_show: 'No-show',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-online-booking-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpOnlineBookingList {
  @State() bookings: Booking[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterStatus = '';
  @State() saving = false;

  // Alta rápida
  @State() newCustomer = '';
  @State() newService = '';
  @State() newDate = '';
  @State() newTime = '';
  @State() newStaff = '';
  @State() newDuration = '30';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'booking_reference', header: 'Ref' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'service_name', header: 'Servicio' },
    { key: 'staff_name', header: 'Personal' },
    { key: 'booking_date', header: 'Fecha' },
    { key: 'booking_time', header: 'Hora', format: (r) => String(r.booking_time ?? '').slice(0, 5) },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
  ];

  private actions = [
    { id: 'confirm', label: 'Confirmar', icon: 'checkmark-outline', color: 'success' },
    { id: 'complete', label: 'Completar', icon: 'checkmark-done-outline', color: 'primary' },
    { id: 'no_show', label: 'No-show', icon: 'close-circle-outline', color: 'medium' },
    { id: 'cancel', label: 'Cancelar', icon: 'ban-outline', color: 'warning' },
    { id: 'delete', label: 'Borrar', icon: 'trash-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        'online_booking.booking.created',
        'online_booking.booking.confirmed',
        'online_booking.booking.cancelled',
        'online_booking.booking.completed',
        'online_booking.booking.no_show',
        'online_booking.booking.deleted',
      ].map((ev) => erplora().on(ev, () => this.refresh()));
      this.unsub = () => offs.forEach((off) => off());
    } catch {
      /* sin SDK (preview) → sin reactividad en vivo */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<Booking[]>('online_booking.bookings.list', {
        status: this.filterStatus,
        booking_date: '',
      });
      this.bookings = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando reservas';
    } finally {
      this.loading = false;
    }
  }

  private async createBooking(ev: Event) {
    ev.preventDefault();
    if (!this.newCustomer.trim() || !this.newService.trim() || !this.newDate || !this.newTime) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('online_booking.bookings.create', {
        customer_name: this.newCustomer.trim(),
        service_name: this.newService.trim(),
        staff_name: this.newStaff.trim(),
        booking_date: this.newDate,
        booking_time: this.newTime.length === 5 ? `${this.newTime}:00` : this.newTime,
        duration_minutes: Number(this.newDuration) || 30,
        booking_type: 'appointment',
        notes: '',
      });
      this.newCustomer = '';
      this.newService = '';
      this.newDate = '';
      this.newTime = '';
      this.newStaff = '';
      this.newDuration = '30';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la reserva';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    const booking_id = String(row.id);
    this.error = '';
    try {
      if (actionId === 'confirm') {
        await erplora().command('online_booking.bookings.confirm', { booking_id });
      } else if (actionId === 'complete') {
        await erplora().command('online_booking.bookings.complete', { booking_id });
      } else if (actionId === 'no_show') {
        await erplora().command('online_booking.bookings.no_show', { booking_id });
      } else if (actionId === 'cancel') {
        await erplora().command('online_booking.bookings.cancel', { booking_id, reason: '' });
      } else if (actionId === 'delete') {
        await erplora().command('online_booking.bookings.delete', { booking_id });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar la reserva';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Reservas online</h2>
          <ion-select
            placeholder="Estado…"
            value={this.filterStatus}
            onIonChange={(e: any) => {
              this.filterStatus = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="pending">Pendiente</ion-select-option>
            <ion-select-option value="confirmed">Confirmada</ion-select-option>
            <ion-select-option value="completed">Completada</ion-select-option>
            <ion-select-option value="cancelled">Cancelada</ion-select-option>
            <ion-select-option value="no_show">No-show</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createBooking(e)}>
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            placeholder="Servicio"
            value={this.newService}
            onIonInput={(e: any) => (this.newService = e.target.value)}
          />
          <ion-input
            placeholder="Personal (opcional)"
            value={this.newStaff}
            onIonInput={(e: any) => (this.newStaff = e.target.value)}
          />
          <ion-input
            type="date"
            value={this.newDate}
            onIonInput={(e: any) => (this.newDate = e.target.value)}
          />
          <ion-input
            type="time"
            value={this.newTime}
            onIonInput={(e: any) => (this.newTime = e.target.value)}
          />
          <ion-input
            type="number"
            min="5"
            step="5"
            placeholder="Min."
            value={this.newDuration}
            onIonInput={(e: any) => (this.newDuration = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCustomer || !this.newService || !this.newDate || !this.newTime}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.bookings as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['booking_reference', 'customer_name', 'service_name', 'staff_name']}
          searchPlaceholder="Buscar ref, cliente, servicio…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin reservas.'}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
