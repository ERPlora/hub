import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_italy` — vista Esterometro. Mini-app: lista
// de líneas transfronterizas (entries) por periodo + alta rápida. Es una de las
// piezas `ui.entry` que el shell carga en runtime
// (modules/fiscal_italy/dist/fiscal_italy.esm.js).
//
// La agregación de la declaración mensual y el flip de estados de las líneas
// vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface EsterometroEntry {
  id: string;
  period_year: number;
  period_month: number;
  transaction_type: string;
  counterparty_country: string;
  counterparty_vat_id: string;
  total_amount: string;
  transaction_date: string;
  document_ref: string;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-italy-esterometro',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:7rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpFiscalItalyEsterometro {
  @State() entries: EsterometroEntry[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterYear = '';
  @State() filterMonth = '';
  @State() newYear = '';
  @State() newMonth = '';
  @State() newType = 'sale';
  @State() newCountry = '';
  @State() newVatId = '';
  @State() newAmount = '';
  @State() newTxDate = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'period_year', header: 'Año' },
    { key: 'period_month', header: 'Mes' },
    { key: 'transaction_type', header: 'Tipo' },
    { key: 'counterparty_country', header: 'País' },
    { key: 'counterparty_vat_id', header: 'VAT ID' },
    { key: 'total_amount', header: 'Importe', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fiscal_italy.esterometro.entry.created', () => this.refresh());
      const off2 = erplora().on('fiscal_italy.esterometro.declaration.generated', () => this.refresh());
      const off3 = erplora().on('fiscal_italy.esterometro.declaration.submitted', () => this.refresh());
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
      const entries = await erplora().query<EsterometroEntry[]>('fiscal_italy.esterometro.entries.list', {
        period_year: Number(this.filterYear) || 0,
        period_month: Number(this.filterMonth) || 0,
      });
      this.entries = entries ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando líneas Esterometro';
    } finally {
      this.loading = false;
    }
  }

  private async createEntry(ev: Event) {
    ev.preventDefault();
    if (!this.newCountry.trim() || !this.newVatId.trim() || !this.newTxDate.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fiscal_italy.esterometro.entry.create', {
        period_year: Number(this.newYear) || 0,
        period_month: Number(this.newMonth) || 0,
        transaction_type: this.newType,
        counterparty_country: this.newCountry.trim().toUpperCase(),
        counterparty_vat_id: this.newVatId.trim(),
        total_amount: Number(this.newAmount) || 0,
        transaction_date: this.newTxDate.trim(),
        document_ref: '',
      });
      this.newCountry = '';
      this.newVatId = '';
      this.newAmount = '';
      this.newTxDate = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar la línea';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Esterometro</h2>
          <ion-input
            type="number"
            placeholder="Año"
            value={this.filterYear}
            onIonInput={(e: any) => {
              this.filterYear = e.target.value;
              this.refresh();
            }}
          />
          <ion-input
            type="number"
            placeholder="Mes"
            value={this.filterMonth}
            onIonInput={(e: any) => {
              this.filterMonth = e.target.value;
              this.refresh();
            }}
          />
        </header>

        <form class="form" onSubmit={(e) => this.createEntry(e)}>
          <ion-input
            type="number"
            placeholder="Año"
            value={this.newYear}
            onIonInput={(e: any) => (this.newYear = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Mes"
            value={this.newMonth}
            onIonInput={(e: any) => (this.newMonth = e.target.value)}
          />
          <ion-select
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="sale">Venta</ion-select-option>
            <ion-select-option value="purchase">Compra</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="País (FR)"
            value={this.newCountry}
            onIonInput={(e: any) => (this.newCountry = e.target.value)}
          />
          <ion-input
            placeholder="VAT ID"
            value={this.newVatId}
            onIonInput={(e: any) => (this.newVatId = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            type="date"
            value={this.newTxDate}
            onIonInput={(e: any) => (this.newTxDate = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCountry || !this.newVatId || !this.newTxDate}
          >
            {this.saving ? 'Guardando…' : 'Registrar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.entries as unknown as Record<string, unknown>[]}
          searchKeys={['counterparty_country', 'counterparty_vat_id', 'transaction_type']}
          searchPlaceholder="Buscar país o VAT ID…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin líneas Esterometro.'}
        />
      </div>
    );
  }
}
