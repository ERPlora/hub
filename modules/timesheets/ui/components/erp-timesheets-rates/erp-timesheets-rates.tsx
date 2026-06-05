import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `timesheets` (Stencil). Vista "Rates": tarifas horarias
// de facturación + alta rápida. NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface HourlyRate {
  id: string;
  name: string;
  rate: string;
  employee_id: string | null;
  is_default: number;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-timesheets-rates',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpTimesheetsRates {
  @State() rates: HourlyRate[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newRate = '';
  @State() newDefault = false;
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'rate', header: '€/h', align: 'right', format: (r) => Number(r.rate).toFixed(2) },
    { key: 'is_default', header: 'Por defecto', format: (r) => (Number(r.is_default) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('timesheets.rate.created', () => this.refresh());
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
      const rows = await erplora().query<HourlyRate[]>('timesheets.rates.list');
      this.rates = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando tarifas';
    } finally {
      this.loading = false;
    }
  }

  private async createRate(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newRate) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('timesheets.rates.create', {
        name: this.newName.trim(),
        rate: Number(this.newRate) || 0,
        employee_id: '',
        is_default: this.newDefault,
      });
      this.newName = '';
      this.newRate = '';
      this.newDefault = false;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la tarifa';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Tarifas horarias</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createRate(e)}>
          <ion-input
            placeholder="Nombre (Senior)"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            min="0"
            placeholder="€/h"
            value={this.newRate}
            onIonInput={(e: any) => (this.newRate = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newRate}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.rates as unknown as Record<string, unknown>[]}
          searchKeys={['name']}
          searchPlaceholder="Buscar tarifa…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin tarifas horarias.'}
        />
      </div>
    );
  }
}
