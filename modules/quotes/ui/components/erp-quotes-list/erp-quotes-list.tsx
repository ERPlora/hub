import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `quotes` (Stencil). Mini-app: lista de cotizaciones +
// filtro por estado + alta rápida (un solo ítem) + acción "enviar". Es la pieza
// `ui.entry` que el shell carga en runtime (modules/quotes/dist/quotes.esm.js).
//
// 90% de la lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El cálculo de líneas/totales y el nº de cotización
// los hace el handler WASM (ver WASM-TODO.md); la UI solo recoge inputs.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot).
// El listado usa el DataTable compartido + el alta usa elementos Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Quote {
  id: string;
  quote_number: string;
  status: string;
  customer_name: string;
  customer_email: string;
  customer_tax_id: string;
  issue_date: string;
  valid_until: string | null;
  total_amount: number;
  tax_amount: number;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  sent: 'Enviada',
  accepted: 'Aceptada',
  rejected: 'Rechazada',
  expired: 'Caducada',
  converted: 'Convertida',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-quotes-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpQuotesList {
  @State() quotes: Quote[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterStatus = '';
  @State() newCustomer = '';
  @State() newDescription = '';
  @State() newPrice = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'quote_number', header: 'Número' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
  ];

  // Acción de fila: solo "Enviar". El DataTable la muestra en todas las filas;
  // el handler ignora las que no estén en borrador (la regla la revalida Rust).
  private actions: DataTableAction[] = [{ id: 'send', label: 'Enviar', color: 'primary' }];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos cuando el runtime emite eventos de dominio de quotes.
    try {
      const events = [
        'quotes.quote.created',
        'quotes.quote.updated',
        'quotes.quote.sent',
        'quotes.quote.accepted',
        'quotes.quote.rejected',
        'quotes.quote.converted',
        'quotes.quote.expired',
      ];
      const offs = events.map((e) => erplora().on(e, () => this.refresh()));
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
      const rows = await erplora().query<Quote[]>('quotes.quotes.list', {
        status: this.filterStatus,
      });
      this.quotes = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando cotizaciones';
    } finally {
      this.loading = false;
    }
  }

  private async onFilterChange(value: string) {
    this.filterStatus = value;
    await this.refresh();
  }

  private async createQuote(ev: Event) {
    ev.preventDefault();
    if (!this.newCustomer.trim() || !this.newDescription.trim()) return;
    this.saving = true;
    try {
      // El handler WASM genera el nº de cotización (counter atómico) y calcula
      // line_total + totales antes de persistir. La UI solo envía la intención.
      await erplora().command('quotes.quotes.create', {
        customer_name: this.newCustomer.trim(),
        customer_email: '',
        customer_tax_id: '',
        valid_until: '',
        notes: '',
        terms_conditions: '',
        lines: [
          {
            description: this.newDescription.trim(),
            quantity: '1',
            unit_price: this.newPrice || '0',
            discount_pct: '0',
            tax_rate: '0',
          },
        ],
      });
      this.newCustomer = '';
      this.newDescription = '';
      this.newPrice = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la cotización';
    } finally {
      this.saving = false;
    }
  }

  private async sendQuote(id: string) {
    try {
      await erplora().command('quotes.quotes.send', { quote_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo enviar';
    }
  }

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    const { actionId, row } = ev.detail;
    if (actionId === 'send' && row.status === 'draft') {
      this.sendQuote(row.id as string);
    }
  };

  render() {
    return (
      <div>
        <header>
          <h2>Cotizaciones</h2>
          <ion-select
            placeholder="Todos los estados"
            value={this.filterStatus}
            interface="popover"
            onIonChange={(e: any) => this.onFilterChange(e.target.value)}
          >
            <ion-select-option value="">Todos los estados</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="sent">Enviada</ion-select-option>
            <ion-select-option value="accepted">Aceptada</ion-select-option>
            <ion-select-option value="rejected">Rechazada</ion-select-option>
            <ion-select-option value="expired">Caducada</ion-select-option>
            <ion-select-option value="converted">Convertida</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createQuote(e)}>
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            placeholder="Concepto"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Precio"
            value={this.newPrice}
            onIonInput={(e: any) => (this.newPrice = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCustomer || !this.newDescription}>
            {this.saving ? 'Guardando…' : 'Nueva cotización'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.quotes as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['quote_number', 'customer_name']}
          searchPlaceholder="Buscar número o cliente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin cotizaciones.'}
          onRowAction={this.onRowAction}
        />
      </div>
    );
  }
}
