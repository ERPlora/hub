import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `financial_statements` (Stencil). Mini-app: lista de plantillas
// de informe (Balance / P&L / Cash Flow / custom) + alta rápida. Pieza `ui.entry` que el
// shell carga en runtime (modules/financial_statements/dist/financial_statements.esm.js).
//
// La lógica de cálculo (generar informes, comparar, exportar) vive en Rust/WASM: este
// componente NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ReportTemplate {
  id: string;
  code: string;
  name: string;
  report_type: string;
  is_default: number;
  is_active: number;
}

const REPORT_TYPES = ['balance_sheet', 'profit_loss', 'cash_flow', 'custom'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-financial-statements-templates',
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
export class ErpFinancialStatementsTemplates {
  @State() templates: ReportTemplate[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'custom';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'report_type', header: 'Tipo' },
    { key: 'is_default', header: 'Por defecto', align: 'center', format: (r) => (r.is_default ? 'Sí' : '') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('financial_statements.template.created', () => this.refresh());
      const off2 = erplora().on('financial_statements.line_item.added', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
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
      const templates = await erplora().query<ReportTemplate[]>('financial_statements.templates.list', {
        report_type: '',
        active_only: 1,
      });
      this.templates = templates ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando plantillas';
    } finally {
      this.loading = false;
    }
  }

  private async createTemplate(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('financial_statements.templates.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        report_type: this.newType,
        structure: {},
        is_default: false,
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'custom';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la plantilla';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Plantillas de informe</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTemplate(e)}>
          <ion-input
            placeholder="Código (balance-2026)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
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
            {REPORT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.templates as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'report_type']}
          searchPlaceholder="Buscar plantilla…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin plantillas.'}
        />
      </div>
    );
  }
}
