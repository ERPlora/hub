import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `sepa_remittances` (vista "mandates"). Mini-app: lista de
// mandatos SEPA + filtro por estado + alta rápida + acción "revocar". Es parte de la
// pieza `ui.entry` que el shell carga en runtime (modules/sepa_remittances/dist/sepa_remittances.esm.js).
//
// La lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El cliente se obtiene de `globalThis.erplora`.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SepaMandate {
  id: string;
  mandate_id: string;
  debtor_name: string;
  debtor_iban: string;
  creditor_id: string;
  scheme: string;
  status: string;
}

const STATUS_LABELS: Record<string, string> = {
  active: 'Activo',
  revoked: 'Revocado',
  expired: 'Caducado',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-sepa-remittances-mandates',
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
export class ErpSepaRemittancesMandates {
  @State() mandates: SepaMandate[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = 'active';
  @State() newMandateId = '';
  @State() newDebtorName = '';
  @State() newDebtorIban = '';
  @State() newCreditorId = '';
  @State() newScheme = 'CORE';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'mandate_id', header: 'UMR' },
    { key: 'debtor_name', header: 'Deudor' },
    { key: 'debtor_iban', header: 'IBAN' },
    { key: 'scheme', header: 'Esquema' },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
  ];

  private actions: DataTableAction[] = [{ id: 'revoke', label: 'Revocar', color: 'danger' }];

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    const { actionId, row } = ev.detail;
    if (actionId === 'revoke' && (row.status as string) === 'active') {
      this.revoke(row as unknown as SepaMandate);
    }
  };

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('sepa_remittances.mandate.created', () => this.refresh());
      const off2 = erplora().on('sepa_remittances.mandate.revoked', () => this.refresh());
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
      const rows = await erplora().query<SepaMandate[]>('sepa_remittances.mandates.list', {
        status: this.statusFilter,
        limit: 100,
      });
      this.mandates = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando mandatos';
    } finally {
      this.loading = false;
    }
  }

  private async onStatusChange(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  private async createMandate(ev: Event) {
    ev.preventDefault();
    if (!this.newMandateId.trim() || !this.newDebtorName.trim() || !this.newDebtorIban.trim() || !this.newCreditorId.trim()) {
      return;
    }
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('sepa_remittances.mandates.create', {
        mandate_id: this.newMandateId.trim(),
        debtor_name: this.newDebtorName.trim(),
        debtor_iban: this.newDebtorIban.trim().toUpperCase(),
        creditor_id: this.newCreditorId.trim(),
        scheme: this.newScheme,
        debtor_bic: '',
        signed_date: null,
        notes: '',
      });
      this.newMandateId = '';
      this.newDebtorName = '';
      this.newDebtorIban = '';
      this.newCreditorId = '';
      this.newScheme = 'CORE';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el mandato';
    } finally {
      this.saving = false;
    }
  }

  private async revoke(m: SepaMandate) {
    this.error = '';
    try {
      await erplora().command('sepa_remittances.mandates.revoke', { mandate_id: m.id, reason: '' });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo revocar el mandato';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Mandatos SEPA</h2>
          <ion-select
            value={this.statusFilter}
            interface="popover"
            onIonChange={(e: any) => this.onStatusChange(e.target.value)}
          >
            <ion-select-option value="active">Activos</ion-select-option>
            <ion-select-option value="revoked">Revocados</ion-select-option>
            <ion-select-option value="expired">Caducados</ion-select-option>
            <ion-select-option value="">Todos</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createMandate(e)}>
          <ion-input
            placeholder="UMR (referencia)"
            value={this.newMandateId}
            onIonInput={(e: any) => (this.newMandateId = e.target.value)}
          />
          <ion-input
            placeholder="Nombre deudor"
            value={this.newDebtorName}
            onIonInput={(e: any) => (this.newDebtorName = e.target.value)}
          />
          <ion-input
            placeholder="IBAN deudor"
            value={this.newDebtorIban}
            onIonInput={(e: any) => (this.newDebtorIban = e.target.value)}
          />
          <ion-input
            placeholder="Creditor Id"
            value={this.newCreditorId}
            onIonInput={(e: any) => (this.newCreditorId = e.target.value)}
          />
          <ion-select
            value={this.newScheme}
            interface="popover"
            onIonChange={(e: any) => (this.newScheme = e.target.value)}
          >
            <ion-select-option value="CORE">CORE</ion-select-option>
            <ion-select-option value="B2B">B2B</ion-select-option>
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newMandateId || !this.newDebtorName || !this.newDebtorIban || !this.newCreditorId}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.mandates as unknown as Record<string, unknown>[]}
          actions={this.actions}
          onRowAction={this.onRowAction}
          searchKeys={['mandate_id', 'debtor_name', 'debtor_iban']}
          searchPlaceholder="Buscar UMR, deudor o IBAN…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin mandatos.'}
        />
      </div>
    );
  }
}
