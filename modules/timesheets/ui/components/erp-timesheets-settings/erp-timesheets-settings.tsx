import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `timesheets` (Stencil). Vista "Settings": configuración
// singleton del módulo (facturable por defecto, requiere aprobación, periodo de
// aprobación). El alta/edición usa el command upsert. NO toca la BD: llama al SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TimesheetsSettings {
  id?: string;
  default_billable: number | boolean;
  require_approval: number | boolean;
  approval_period: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-timesheets-settings',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:1rem; flex-wrap:wrap; align-items:center; margin:.5rem 0 1.5rem; }
    .field { display:flex; gap:.4rem; align-items:center; }
    .field ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpTimesheetsSettings {
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() defaultBillable = true;
  @State() requireApproval = true;
  @State() approvalPeriod = 'weekly';

  private columns: DataTableColumn[] = [
    { key: 'default_billable', header: 'Facturable por defecto', format: (r) => (Number(r.default_billable) ? 'Sí' : 'No') },
    { key: 'require_approval', header: 'Requiere aprobación', format: (r) => (Number(r.require_approval) ? 'Sí' : 'No') },
    { key: 'approval_period', header: 'Periodo' },
  ];

  async componentWillLoad() {
    await this.refresh();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<TimesheetsSettings[]>('timesheets.settings.get');
      const s = rows?.[0];
      if (s) {
        this.defaultBillable = !!Number(s.default_billable);
        this.requireApproval = !!Number(s.require_approval);
        this.approvalPeriod = s.approval_period || 'weekly';
      }
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando configuración';
    } finally {
      this.loading = false;
    }
  }

  private async save(ev: Event) {
    ev.preventDefault();
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('timesheets.settings.update', {
        default_billable: this.defaultBillable,
        require_approval: this.requireApproval,
        approval_period: this.approvalPeriod,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo guardar la configuración';
    } finally {
      this.saving = false;
    }
  }

  render() {
    const summary = [
      {
        default_billable: this.defaultBillable ? 1 : 0,
        require_approval: this.requireApproval ? 1 : 0,
        approval_period: this.approvalPeriod,
      },
    ];
    return (
      <div>
        <header>
          <h2>Configuración de timesheets</h2>
        </header>

        <form class="form" onSubmit={(e) => this.save(e)}>
          <div class="field">
            <ion-toggle
              checked={this.defaultBillable}
              onIonChange={(e: any) => (this.defaultBillable = e.target.checked)}
            />
            <ion-label>Facturable por defecto</ion-label>
          </div>
          <div class="field">
            <ion-toggle
              checked={this.requireApproval}
              onIonChange={(e: any) => (this.requireApproval = e.target.checked)}
            />
            <ion-label>Requiere aprobación</ion-label>
          </div>
          <div class="field">
            <ion-label>Periodo</ion-label>
            <ion-select
              value={this.approvalPeriod}
              onIonChange={(e: any) => (this.approvalPeriod = e.target.value)}
            >
              <ion-select-option value="weekly">Semanal</ion-select-option>
              <ion-select-option value="biweekly">Quincenal</ion-select-option>
              <ion-select-option value="monthly">Mensual</ion-select-option>
            </ion-select>
          </div>
          <ion-button type="submit" size="small" disabled={this.saving}>
            {this.saving ? 'Guardando…' : 'Guardar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={summary as unknown as Record<string, unknown>[]}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin configuración.'}
        />
      </div>
    );
  }
}
