import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `invoice_series` (Stencil). Mini-app: lista de series de
// numeración fiscal + alta rápida + acción "Siguiente número". Es la pieza `ui.entry`
// que el shell carga en runtime (modules/invoice_series/dist/invoice_series.esm.js).
//
// 90% de la lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). La asignación atómica de números, el renderizado de la
// plantilla (format_number) y el degradado de la default los valida y ejecuta el runtime.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot).
// El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Series {
  id: string;
  code: string;
  name: string;
  document_type: string;
  prefix: string;
  fiscal_year: number;
  current_sequence: number;
  is_default: number;
  is_active: number;
}

const DOCUMENT_TYPES = ['invoice', 'credit_note', 'proforma', 'receipt', 'quote'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-invoice-series-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpInvoiceSeriesList {
  @State() series: Series[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newCode = '';
  @State() newName = '';
  @State() newPrefix = '';
  @State() newDocType = 'invoice';
  @State() newCountry = '';
  @State() newYear = String(new Date().getFullYear());

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    {
      key: 'code',
      header: 'Código',
      format: (r) => `${r.code as string}${r.is_default ? '  ★' : ''}`,
    },
    { key: 'name', header: 'Nombre' },
    { key: 'document_type', header: 'Tipo' },
    { key: 'fiscal_year', header: 'Año', align: 'right' },
    { key: 'current_sequence', header: 'Secuencia', align: 'right' },
  ];

  private actions = [
    { id: 'next', label: 'Siguiente nº', icon: 'arrow-forward' },
    { id: 'default', label: 'Por defecto', icon: 'star', color: 'medium' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos cuando el runtime emite cambios de serie o
    // se asigna un número (la secuencia avanza).
    try {
      const offs = [
        erplora().on('invoice_series.series.created', () => this.refresh()),
        erplora().on('invoice_series.series.updated', () => this.refresh()),
        erplora().on('invoice_series.series.deactivated', () => this.refresh()),
        erplora().on('invoice_series.series.default_changed', () => this.refresh()),
        erplora().on('invoice_series.number.allocated', () => this.refresh()),
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
      const rows = await erplora().query<Series[]>('invoice_series.series.list', {
        document_type: '',
        country_code: '',
        active_only: 0,
      });
      this.series = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando series';
    } finally {
      this.loading = false;
    }
  }

  private async createSeries(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim() || !this.newPrefix.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('invoice_series.series.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        document_type: this.newDocType,
        prefix: this.newPrefix.trim(),
        suffix: '',
        format: '{prefix}-{year}-{seq:05d}',
        country_code: this.newCountry.trim(),
        region_code: '',
        fiscal_year: Number(this.newYear) || new Date().getFullYear(),
        is_default: 0,
      });
      this.newCode = '';
      this.newName = '';
      this.newPrefix = '';
      this.newCountry = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la serie';
    } finally {
      this.saving = false;
    }
  }

  private async nextNumber(id: string) {
    this.error = '';
    try {
      await erplora().command('invoice_series.series.next_number', { series_id: id, document_ref: '' });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo asignar el número';
    }
  }

  private async setDefault(id: string) {
    this.error = '';
    try {
      await erplora().command('invoice_series.series.set_default', { series_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo marcar por defecto';
    }
  }

  private onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    const s = row as unknown as Series;
    if (actionId === 'next') {
      if (s.is_active) this.nextNumber(s.id);
    } else if (actionId === 'default') {
      if (s.is_active && !s.is_default) this.setDefault(s.id);
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Series de numeración</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createSeries(e)}>
          <ion-input
            placeholder="Código"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Prefijo"
            value={this.newPrefix}
            onIonInput={(e: any) => (this.newPrefix = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newDocType}
            onIonChange={(e: any) => (this.newDocType = e.target.value)}
          >
            {DOCUMENT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="País"
            value={this.newCountry}
            onIonInput={(e: any) => (this.newCountry = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Año"
            value={this.newYear}
            onIonInput={(e: any) => (this.newYear = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCode || !this.newName || !this.newPrefix}
          >
            {this.saving ? 'Guardando…' : 'Crear serie'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.series as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'document_type']}
          searchPlaceholder="Buscar código o nombre…"
          actions={this.actions}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin series.'}
        />
      </div>
    );
  }
}
