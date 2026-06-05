import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `customer_portal` (Stencil). Mini-app: cuentas del portal
// self-service de clientes finales + invitación rápida + acciones de ciclo de vida
// (suspender/reactivar/cerrar). Pieza `ui.entry` que el shell carga en runtime
// (modules/customer_portal/dist/customer_portal.esm.js).
//
// La lógica real (hashing de password, tokens, expiración, flujo de accept) vive en
// Rust/WASM: este componente NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CustomerAccount {
  id: string;
  customer_name: string;
  customer_email: string;
  customer_tax_id: string;
  status: string;
  email_verified: number;
  language: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-customer-portal-accounts',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .actions { display:flex; gap:.25rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCustomerPortalAccounts {
  @State() accounts: CustomerAccount[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newEmail = '';
  @State() newName = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'customer_name', header: 'Nombre' },
    { key: 'customer_email', header: 'Email' },
    { key: 'status', header: 'Estado' },
    { key: 'email_verified', header: 'Verificado', format: (r) => (r.email_verified ? 'Sí' : 'No') },
    { key: 'language', header: 'Idioma' },
    {
      key: 'id',
      header: 'Acciones',
      format: (r) => this.renderActions(r as unknown as CustomerAccount),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('customer_portal.invitation.created', () => this.refresh()),
        erplora().on('customer_portal.account.activated', () => this.refresh()),
        erplora().on('customer_portal.account.suspended', () => this.refresh()),
        erplora().on('customer_portal.account.reactivated', () => this.refresh()),
        erplora().on('customer_portal.account.closed', () => this.refresh()),
      ];
      this.unsub = () => offs.forEach((o) => o());
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
      const accounts = await erplora().query<CustomerAccount[]>('customer_portal.accounts.list', {
        status: this.statusFilter,
      });
      this.accounts = accounts ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando cuentas';
    } finally {
      this.loading = false;
    }
  }

  private async invite(ev: Event) {
    ev.preventDefault();
    if (!this.newEmail.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('customer_portal.invitations.create', {
        customer_email: this.newEmail.trim(),
        customer_name: this.newName.trim(),
        invited_by_ref: '',
      });
      this.newEmail = '';
      this.newName = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la invitación';
    } finally {
      this.saving = false;
    }
  }

  private async lifecycle(account: CustomerAccount, action: 'suspend' | 'reactivate' | 'close') {
    this.error = '';
    try {
      await erplora().command(`customer_portal.accounts.${action}`, { account_id: account.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar la cuenta';
    }
  }

  private renderActions(account: CustomerAccount) {
    return (
      <span class="actions">
        {account.status === 'active' && (
          <ion-button size="small" fill="outline" onClick={() => this.lifecycle(account, 'suspend')}>
            Suspender
          </ion-button>
        )}
        {account.status === 'suspended' && (
          <ion-button size="small" fill="outline" onClick={() => this.lifecycle(account, 'reactivate')}>
            Reactivar
          </ion-button>
        )}
        {account.status !== 'closed' && (
          <ion-button size="small" color="danger" fill="outline" onClick={() => this.lifecycle(account, 'close')}>
            Cerrar
          </ion-button>
        )}
      </span>
    );
  }

  render() {
    return (
      <div>
        <header>
          <h2>Cuentas del portal</h2>
          <ion-select
            placeholder="Todos"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="invited">Invitados</ion-select-option>
            <ion-select-option value="active">Activos</ion-select-option>
            <ion-select-option value="suspended">Suspendidos</ion-select-option>
            <ion-select-option value="closed">Cerrados</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.invite(e)}>
          <ion-input
            placeholder="Email del cliente"
            value={this.newEmail}
            onIonInput={(e: any) => (this.newEmail = e.target.value)}
          />
          <ion-input
            placeholder="Nombre (opcional)"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newEmail}>
            {this.saving ? 'Enviando…' : 'Invitar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.accounts as unknown as Record<string, unknown>[]}
          searchKeys={['customer_name', 'customer_email']}
          searchPlaceholder="Buscar nombre o email…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin cuentas.'}
        />
      </div>
    );
  }
}
