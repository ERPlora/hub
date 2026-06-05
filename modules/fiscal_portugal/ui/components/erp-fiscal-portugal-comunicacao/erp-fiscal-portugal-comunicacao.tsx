import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_portugal` (vista Comunicação à AT). Mini-app:
// lista de comunicaciones a la AT (faturas / transporte / inventario) + alta de un
// borrador y acción de envío. Es una de las piezas que el shell carga desde dist/.
//
// Toda la lógica (autonumeración ATC-YYYYMMDD-NNNN, XML, composición de submission_id,
// máquina de estados) vive en el handler WASM — este componente NO toca la BD; llama
// al SDK (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AtCommunication {
  id: string;
  document_number: string;
  communication_type: string;
  reference_period: string;
  submission_id: string;
  status: string;
  submitted_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-portugal-comunicacao',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpFiscalPortugalComunicacao {
  @State() comms: AtCommunication[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newType = 'invoice';
  @State() newPeriod = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Documento' },
    { key: 'communication_type', header: 'Tipo' },
    { key: 'reference_period', header: 'Período' },
    { key: 'submission_id', header: 'ID AT' },
    { key: 'status', header: 'Estado' },
  ];

  private actions: DataTableAction[] = [
    { id: 'submit', label: 'Enviar', color: 'primary' },
    { id: 'accept', label: 'Aceptar', color: 'success' },
    { id: 'reject', label: 'Rechazar', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fiscal_portugal.at_comm.created', () => this.refresh());
      const off2 = erplora().on('fiscal_portugal.at_comm.submitted', () => this.refresh());
      const off3 = erplora().on('fiscal_portugal.at_comm.status_changed', () => this.refresh());
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
      const rows = await erplora().query<AtCommunication[]>('fiscal_portugal.at_comm.list', {
        status: this.statusFilter,
      });
      this.comms = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando comunicaciones AT';
    } finally {
      this.loading = false;
    }
  }

  private async create(ev: Event) {
    ev.preventDefault();
    if (!this.newPeriod.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fiscal_portugal.at_comm.create', {
        communication_type: this.newType,
        reference_period: this.newPeriod.trim(),
        content_data: {},
      });
      this.newPeriod = '';
      this.newType = 'invoice';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la comunicación';
    } finally {
      this.saving = false;
    }
  }

  private async onAction(actionId: string, row: AtCommunication) {
    this.error = '';
    try {
      if (actionId === 'submit') {
        if (row.status !== 'draft') return;
        await erplora().command('fiscal_portugal.at_comm.submit', { comm_id: row.id });
      } else if (actionId === 'accept' || actionId === 'reject') {
        await erplora().command('fiscal_portugal.at_comm.set_status', {
          comm_id: row.id,
          new_status: actionId === 'accept' ? 'accepted' : 'rejected',
        });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar la comunicación';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Comunicações à AT</h2>
        </header>

        <form class="form" onSubmit={(e) => this.create(e)}>
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="invoice">Faturas</ion-select-option>
            <ion-select-option value="transport">Transporte</ion-select-option>
            <ion-select-option value="inventory">Inventario</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="Período (2026-01)"
            value={this.newPeriod}
            onIonInput={(e: any) => (this.newPeriod = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newPeriod}>
            {this.saving ? 'Creando…' : 'Crear borrador'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.comms as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'communication_type', 'status', 'reference_period']}
          searchPlaceholder="Buscar documento, tipo o estado…"
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            this.onAction(e.detail.actionId, e.detail.row as unknown as AtCommunication)
          }
          emptyMessage={this.loading ? 'Cargando…' : 'Sin comunicaciones AT.'}
        />
      </div>
    );
  }
}
