import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `payroll` (Stencil). Mini-app: lista de conceptos de
// nómina (devengos/deducciones) + alta rápida. Pieza `ui.entry` que el shell
// carga en runtime (modules/payroll/dist/payroll.esm.js).
//
// El componente NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Concept {
  id: string;
  name: string;
  type: string;
  is_percentage: number;
  amount: string;
  percentage: string;
  is_taxable: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-payroll-concepts',
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
export class ErpPayrollConcepts {
  @State() concepts: Concept[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() typeFilter = '';
  @State() newName = '';
  @State() newType = 'earning';
  @State() newAmount = '';
  @State() newPct = '';
  @State() newIsPct = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Concepto' },
    { key: 'type', header: 'Tipo', format: (r) => (r.type === 'earning' ? 'Devengo' : 'Deducción') },
    {
      key: 'amount',
      header: 'Valor',
      align: 'right',
      format: (r) => (r.is_percentage ? `${Number(r.percentage).toFixed(2)}%` : Number(r.amount).toFixed(2)),
    },
    { key: 'is_taxable', header: 'Tributa', format: (r) => (r.is_taxable ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('payroll.concept.created', () => this.refresh());
      this.unsub = off;
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
      const rows = await erplora().query<Concept[]>('payroll.concepts.list', { concept_type: this.typeFilter });
      this.concepts = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando conceptos';
    } finally {
      this.loading = false;
    }
  }

  private async createConcept(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('payroll.concepts.create', {
        name: this.newName.trim(),
        type: this.newType,
        is_percentage: this.newIsPct,
        amount: Number(this.newAmount) || 0,
        percentage: Number(this.newPct) || 0,
        is_taxable: true,
        sort_order: 0,
      });
      this.newName = '';
      this.newAmount = '';
      this.newPct = '';
      this.newIsPct = false;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el concepto';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Conceptos de nómina</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createConcept(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="earning">Devengo</ion-select-option>
            <ion-select-option value="deduction">Deducción</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="% (opcional)"
            value={this.newPct}
            onIonInput={(e: any) => {
              this.newPct = e.target.value;
              this.newIsPct = !!e.target.value;
            }}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.concepts as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'type']}
          searchPlaceholder="Buscar concepto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin conceptos.'}
        />
      </div>
    );
  }
}
