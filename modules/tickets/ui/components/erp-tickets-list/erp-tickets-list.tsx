import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `tickets` (Stencil). Mini-app: lista de tickets de soporte
// con filtros + alta rápida. Es la pieza `ui.entry` que el shell carga en runtime
// (modules/tickets/dist/tickets.esm.js).
//
// Toda la lógica (numeración TCK-…, máquina de estados, SLA) vive en el handler WASM:
// este componente NO toca la BD; solo llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Ticket {
  id: string;
  ticket_number: string;
  subject: string;
  customer_name: string;
  status: string;
  priority: string;
  category: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-tickets-list',
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
export class ErpTicketsList {
  @State() tickets: Ticket[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() priorityFilter = '';
  @State() newSubject = '';
  @State() newCustomer = '';
  @State() newPriority = 'medium';
  @State() newCategory = 'general';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'ticket_number', header: 'Nº' },
    { key: 'subject', header: 'Asunto' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'priority', header: 'Prioridad' },
    { key: 'status', header: 'Estado' },
    { key: 'category', header: 'Categoría' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('tickets.ticket.created', () => this.refresh());
      const off2 = erplora().on('tickets.ticket.status_changed', () => this.refresh());
      const off3 = erplora().on('tickets.ticket.assigned', () => this.refresh());
      const off4 = erplora().on('tickets.ticket.resolved', () => this.refresh());
      const off5 = erplora().on('tickets.ticket.closed', () => this.refresh());
      const off6 = erplora().on('tickets.ticket.reopened', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
        off5();
        off6();
      };
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
      const tickets = await erplora().query<Ticket[]>('tickets.tickets.list', {
        status: this.statusFilter,
        priority: this.priorityFilter,
        assigned_to: '',
        customer_name: '',
        limit: 50,
      });
      this.tickets = tickets ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando tickets';
    } finally {
      this.loading = false;
    }
  }

  private async createTicket(ev: Event) {
    ev.preventDefault();
    if (!this.newSubject.trim() || !this.newCustomer.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('tickets.tickets.create', {
        subject: this.newSubject.trim(),
        description: '',
        customer_name: this.newCustomer.trim(),
        customer_email: '',
        customer_phone: '',
        priority: this.newPriority,
        category: this.newCategory,
        created_by_ref: '',
      });
      this.newSubject = '';
      this.newCustomer = '';
      this.newPriority = 'medium';
      this.newCategory = 'general';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el ticket';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Tickets</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTicket(e)}>
          <ion-input
            placeholder="Asunto"
            value={this.newSubject}
            onIonInput={(e: any) => (this.newSubject = e.target.value)}
          />
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-select
            value={this.newPriority}
            onIonChange={(e: any) => (this.newPriority = e.target.value)}
          >
            <ion-select-option value="low">Baja</ion-select-option>
            <ion-select-option value="medium">Media</ion-select-option>
            <ion-select-option value="high">Alta</ion-select-option>
            <ion-select-option value="urgent">Urgente</ion-select-option>
          </ion-select>
          <ion-select
            value={this.newCategory}
            onIonChange={(e: any) => (this.newCategory = e.target.value)}
          >
            <ion-select-option value="general">General</ion-select-option>
            <ion-select-option value="billing">Facturación</ion-select-option>
            <ion-select-option value="technical">Técnico</ion-select-option>
            <ion-select-option value="feature_request">Mejora</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSubject || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Nuevo ticket'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.tickets as unknown as Record<string, unknown>[]}
          searchKeys={['ticket_number', 'subject', 'customer_name']}
          searchPlaceholder="Buscar nº, asunto o cliente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin tickets.'}
        />
      </div>
    );
  }
}
