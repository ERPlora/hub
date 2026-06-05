import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `credit_risk` (Stencil). Vista de alertas de crédito:
// lista filtrable por severidad / acuse, con acción de "acusar" por fila. Es una pieza
// `ui.entry` que el shell carga en runtime (modules/credit_risk/dist/credit_risk.esm.js).
//
// El WC NO toca la BD: lee vía erplora.query y acusa vía erplora.command.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CreditAlert {
  id: string;
  customer_credit_id: string;
  alert_type: string;
  severity: string;
  triggered_at: string;
  acknowledged_at: string | null;
  acknowledged_by_ref: string;
  notes: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-credit-risk-alerts',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; flex-wrap:wrap; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCreditRiskAlerts {
  @State() alerts: CreditAlert[] = [];
  @State() loading = true;
  @State() error = '';
  @State() severityFilter = '';
  @State() ackFilter = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'triggered_at', header: 'Disparada', format: (r) => String(r.triggered_at ?? '').slice(0, 16).replace('T', ' ') },
    { key: 'alert_type', header: 'Tipo' },
    { key: 'severity', header: 'Severidad' },
    { key: 'acknowledged_at', header: 'Acuse', format: (r) => (r.acknowledged_at ? 'Sí' : '—') },
  ];

  private actions: DataTableAction[] = [{ id: 'ack', label: 'Acusar', icon: 'checkmark-outline' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('credit_risk.alert.triggered', () => this.refresh());
      const off2 = erplora().on('credit_risk.alert.acknowledged', () => this.refresh());
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
      const rows = await erplora().query<CreditAlert[]>('credit_risk.alerts.list', {
        severity: this.severityFilter,
        acknowledged: this.ackFilter,
      });
      this.alerts = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando alertas';
    } finally {
      this.loading = false;
    }
  }

  private async acknowledge(a: CreditAlert) {
    if (a.acknowledged_at) return;
    this.error = '';
    try {
      await erplora().command('credit_risk.alerts.acknowledge', { alert_id: a.id, notes: '' });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo acusar la alerta';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Alertas de crédito</h2>
          <ion-select
            placeholder="Severidad…"
            value={this.severityFilter}
            onIonChange={(e: any) => {
              this.severityFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas</ion-select-option>
            <ion-select-option value="info">Info</ion-select-option>
            <ion-select-option value="warning">Aviso</ion-select-option>
            <ion-select-option value="critical">Crítica</ion-select-option>
          </ion-select>
          <ion-select
            placeholder="Acuse…"
            value={this.ackFilter}
            onIonChange={(e: any) => {
              this.ackFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas</ion-select-option>
            <ion-select-option value="false">Sin acusar</ion-select-option>
            <ion-select-option value="true">Acusadas</ion-select-option>
          </ion-select>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.alerts as unknown as Record<string, unknown>[]}
          searchKeys={['alert_type', 'severity']}
          searchPlaceholder="Buscar tipo o severidad…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin alertas.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            this.acknowledge(e.detail.row as unknown as CreditAlert)
          }
        />
      </div>
    );
  }
}
