import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo empaquete
// dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles, SIEMPRE.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `project_billing` (Stencil). Vista de facturas de proyecto: lista
// (DataTable compartido) + acciones de ciclo de vida (marcar enviada / pagada) vía erplora.command.
// La generación de facturas (rollup de hitos + horas) la dispara la vista de contratos /
// el handler WASM; aquí solo se listan y se transicionan. Este componente NUNCA toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ProjectInvoice {
  id: string;
  contract_id: string;
  invoice_number: string;
  invoice_date: string | null;
  due_date: string | null;
  amount: string;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-project-billing-invoices',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
    .row-actions { display:flex; gap:.35rem; }
  `,
})
export class ErpProjectBillingInvoices {
  @State() invoices: ProjectInvoice[] = [];
  @State() loading = true;
  @State() error = '';
  @State() busy = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'invoice_number', header: 'Nº factura' },
    { key: 'invoice_date', header: 'Fecha' },
    { key: 'due_date', header: 'Vencimiento' },
    { key: 'amount', header: 'Importe', align: 'right', format: (r) => Number(r.amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
    {
      key: 'id',
      header: 'Acciones',
      format: (r) => this.renderActions(r as unknown as ProjectInvoice),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('project_billing.invoice.generated', () => this.refresh());
      const off2 = erplora().on('project_billing.invoice.sent', () => this.refresh());
      const off3 = erplora().on('project_billing.invoice.paid', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
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
      this.invoices =
        (await erplora().query<ProjectInvoice[]>('project_billing.invoices.list', {
          status: '',
          contract_id: '',
          limit: 50,
        })) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando facturas';
    } finally {
      this.loading = false;
    }
  }

  private async markSent(id: string) {
    this.busy = id;
    this.error = '';
    try {
      await erplora().command('project_billing.invoices.mark_sent', { invoice_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo marcar enviada';
    } finally {
      this.busy = '';
    }
  }

  private async markPaid(id: string) {
    this.busy = id;
    this.error = '';
    try {
      await erplora().command('project_billing.invoices.mark_paid', { invoice_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo marcar pagada';
    } finally {
      this.busy = '';
    }
  }

  private renderActions(inv: ProjectInvoice) {
    const disabled = this.busy === inv.id;
    return (
      <span class="row-actions">
        {inv.status === 'draft' && (
          <ion-button size="small" fill="outline" disabled={disabled} onClick={() => this.markSent(inv.id)}>
            Enviar
          </ion-button>
        )}
        {(inv.status === 'draft' || inv.status === 'sent') && (
          <ion-button size="small" disabled={disabled} onClick={() => this.markPaid(inv.id)}>
            Pagar
          </ion-button>
        )}
      </span>
    );
  }

  render() {
    return (
      <div>
        <header>
          <h2>Facturas de proyecto</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.invoices as unknown as Record<string, unknown>[]}
          searchKeys={['invoice_number', 'status']}
          searchPlaceholder="Buscar factura o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin facturas.'}
        />
      </div>
    );
  }
}
