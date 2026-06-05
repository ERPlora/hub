import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `collections` (Stencil). Mini-app: libro de cobros
// entrantes con alta rápida y asignación a facturas. Es la pieza `ui.entry` que
// el shell carga en runtime (modules/collections/dist/collections.esm.js).
//
// El componente NUNCA toca la BD: lee vía erplora.query y muta vía erplora.command.
// Toda la lógica (referencia COL-…, aritmética de asignación, transiciones de
// estado, rastro en notes) vive en el handler WASM (ver WASM-TODO.md).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Collection {
  id: string;
  reference: string;
  collection_date: string;
  amount: string;
  currency: string;
  payer_name: string;
  payer_iban: string;
  concept: string;
  method: string;
  status: string;
  notes: string;
}

const METHOD_LABELS: Record<string, string> = {
  transfer: 'Transferencia',
  card: 'Tarjeta',
  cash: 'Efectivo',
  sepa: 'SEPA',
  other: 'Otro',
};

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente',
  allocated: 'Asignado',
  refunded: 'Reembolsado',
  cancelled: 'Cancelado',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-collections-list',
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
export class ErpCollectionsList {
  @State() collections: Collection[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  // Alta rápida
  @State() newDate = '';
  @State() newAmount = '';
  @State() newPayer = '';
  @State() newConcept = '';
  @State() newMethod = 'transfer';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'reference', header: 'Referencia' },
    { key: 'collection_date', header: 'Fecha' },
    { key: 'payer_name', header: 'Pagador' },
    { key: 'method', header: 'Método', format: (r) => METHOD_LABELS[r.method as string] ?? (r.method as string) },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
    { key: 'amount', header: 'Importe', align: 'right', format: (r) => `${Number(r.amount).toFixed(2)} ${r.currency}` },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('collections.collection.created', () => this.refresh()),
        erplora().on('collections.allocation.created', () => this.refresh()),
        erplora().on('collections.allocation.removed', () => this.refresh()),
        erplora().on('collections.collection.refunded', () => this.refresh()),
        erplora().on('collections.collection.cancelled', () => this.refresh()),
      ];
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
      const rows = await erplora().query<Collection[]>('collections.collections.list', {
        status: this.statusFilter,
        payer_name: '',
      });
      this.collections = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando cobros';
    } finally {
      this.loading = false;
    }
  }

  private async createCollection(ev: Event) {
    ev.preventDefault();
    if (!this.newDate.trim() || !this.newAmount.trim() || !this.newPayer.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('collections.collections.create', {
        collection_date: this.newDate.trim(),
        amount: this.newAmount.trim(),
        payer_name: this.newPayer.trim(),
        concept: this.newConcept.trim(),
        payer_iban: '',
        method: this.newMethod,
        currency: 'EUR',
      });
      this.newDate = '';
      this.newAmount = '';
      this.newPayer = '';
      this.newConcept = '';
      this.newMethod = 'transfer';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el cobro';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Cobros</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createCollection(e)}>
          <ion-input
            type="date"
            placeholder="Fecha"
            value={this.newDate}
            onIonInput={(e: any) => (this.newDate = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            placeholder="Pagador"
            value={this.newPayer}
            onIonInput={(e: any) => (this.newPayer = e.target.value)}
          />
          <ion-input
            placeholder="Concepto"
            value={this.newConcept}
            onIonInput={(e: any) => (this.newConcept = e.target.value)}
          />
          <ion-select
            placeholder="Método…"
            value={this.newMethod}
            onIonChange={(e: any) => (this.newMethod = e.target.value)}
          >
            {Object.keys(METHOD_LABELS).map((m) => (
              <ion-select-option value={m} key={m}>
                {METHOD_LABELS[m]}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newDate || !this.newAmount || !this.newPayer}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.collections as unknown as Record<string, unknown>[]}
          searchKeys={['reference', 'payer_name', 'concept']}
          searchPlaceholder="Buscar referencia, pagador o concepto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin cobros.'}
        />
      </div>
    );
  }
}
