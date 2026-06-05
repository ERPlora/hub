import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `commissions` — vista "Rules". Lista las reglas de comisión
// y permite alta rápida. NO toca la BD: usa el SDK (erplora.query/command/on).
// El cálculo de comisión por regla (flat/percentage/tiered) vive en WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CommissionRule {
  id: string;
  name: string;
  rule_type: string;
  rate: string;
  priority: number;
  effective_from: string | null;
  effective_until: string | null;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-commissions-rules',
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
export class ErpCommissionsRules {
  @State() rules: CommissionRule[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newType = 'percentage';
  @State() newRate = '';
  @State() newPriority = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'rule_type', header: 'Tipo' },
    { key: 'rate', header: 'Tasa', align: 'right', format: (r) => Number(r.rate).toFixed(2) },
    { key: 'priority', header: 'Prioridad', align: 'right' },
    { key: 'is_active', header: 'Activa', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('commissions.rule.created', () => this.refresh());
      const off2 = erplora().on('commissions.rule.updated', () => this.refresh());
      const off3 = erplora().on('commissions.rule.deleted', () => this.refresh());
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
      const rules = await erplora().query<CommissionRule[]>('commissions.rules.list', { only_active: '0' });
      this.rules = rules ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando reglas';
    } finally {
      this.loading = false;
    }
  }

  private async createRule(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newRate) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('commissions.rules.create', {
        name: this.newName.trim(),
        description: '',
        rule_type: this.newType,
        rate: Number(this.newRate) || 0,
        tier_thresholds: '[]',
        priority: Number(this.newPriority) || 0,
      });
      this.newName = '';
      this.newRate = '';
      this.newPriority = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la regla';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Reglas de comisión</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createRule(e)}>
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
            <ion-select-option value="percentage">Porcentaje</ion-select-option>
            <ion-select-option value="flat">Importe fijo</ion-select-option>
            <ion-select-option value="tiered">Por tramos</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            step="0.01"
            placeholder="Tasa"
            value={this.newRate}
            onIonInput={(e: any) => (this.newRate = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Prioridad"
            value={this.newPriority}
            onIonInput={(e: any) => (this.newPriority = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newRate}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.rules as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'rule_type']}
          searchPlaceholder="Buscar regla…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin reglas de comisión.'}
        />
      </div>
    );
  }
}
