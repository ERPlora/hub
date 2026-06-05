import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `kpis` (Stencil). Mini-app: lista de alertas (por defecto
// las no reconocidas) + acción de reconocer (acknowledge). Pieza `ui.entry` cargada
// por el shell en runtime. NO toca la BD; usa el SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface KpiAlert {
  id: string;
  kpi_id: string;
  value_id: string;
  alert_type: string;
  triggered_at: string;
  message: string;
  acknowledged_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-kpis-alerts',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpKpisAlerts {
  @State() alerts: KpiAlert[] = [];
  @State() loading = true;
  @State() error = '';
  @State() acking = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'triggered_at', header: 'Disparada' },
    { key: 'alert_type', header: 'Tipo' },
    { key: 'message', header: 'Mensaje' },
  ];

  private actions: DataTableAction[] = [
    { id: 'ack', label: 'Reconocer', icon: 'checkmark-outline', color: 'primary' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('kpis.alert.raised', () => this.refresh());
      const off2 = erplora().on('kpis.alert.acknowledged', () => this.refresh());
      const off3 = erplora().on('kpis.value.recorded', () => this.refresh());
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
      const alerts = await erplora().query<KpiAlert[]>('kpis.alerts.list', {
        only_unack: 1,
        kpi_id: '',
        alert_type: '',
      });
      this.alerts = alerts ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando alertas';
    } finally {
      this.loading = false;
    }
  }

  private async acknowledge(alertId: string) {
    if (!alertId || this.acking) return;
    this.acking = alertId;
    this.error = '';
    try {
      await erplora().command('kpis.alerts.acknowledge', {
        alert_id: alertId,
        notes: null,
        acknowledged_by_ref: null,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo reconocer la alerta';
    } finally {
      this.acking = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Alertas de KPI</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.alerts as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['alert_type', 'message']}
          searchPlaceholder="Buscar alerta…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin alertas pendientes.'}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            e.detail.actionId === 'ack' && this.acknowledge(e.detail.row.id as string)
          }
        />
      </div>
    );
  }
}
