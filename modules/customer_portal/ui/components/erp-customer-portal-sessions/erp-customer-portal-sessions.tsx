import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `customer_portal` (Stencil). Vista de sesiones activas del
// portal de clientes + revocación. NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface PortalSession {
  id: string;
  account_id: string;
  session_token: string;
  expires_at: string;
  is_active: number;
  ip_address: string;
  user_agent: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-customer-portal-sessions',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCustomerPortalSessions {
  @State() sessions: PortalSession[] = [];
  @State() loading = true;
  @State() error = '';
  @State() activeOnly = 1;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'account_id', header: 'Cuenta' },
    { key: 'ip_address', header: 'IP' },
    { key: 'user_agent', header: 'Cliente' },
    { key: 'expires_at', header: 'Expira' },
    { key: 'is_active', header: 'Activa', format: (r) => (r.is_active ? 'Sí' : 'No') },
    {
      key: 'id',
      header: 'Acciones',
      format: (r) => this.renderActions(r as unknown as PortalSession),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('customer_portal.session.created', () => this.refresh()),
        erplora().on('customer_portal.session.revoked', () => this.refresh()),
        erplora().on('customer_portal.sessions.cleaned', () => this.refresh()),
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
      const sessions = await erplora().query<PortalSession[]>('customer_portal.sessions.list', {
        account_id: '',
        active_only: this.activeOnly,
      });
      this.sessions = sessions ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando sesiones';
    } finally {
      this.loading = false;
    }
  }

  private async revoke(session: PortalSession) {
    this.error = '';
    try {
      await erplora().command('customer_portal.sessions.revoke', { session_id: session.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo revocar la sesión';
    }
  }

  private async cleanup() {
    this.error = '';
    try {
      await erplora().command('customer_portal.sessions.cleanup_expired', {});
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo limpiar sesiones';
    }
  }

  private renderActions(session: PortalSession) {
    if (!session.is_active) return <span>—</span>;
    return (
      <ion-button size="small" color="danger" fill="outline" onClick={() => this.revoke(session)}>
        Revocar
      </ion-button>
    );
  }

  render() {
    return (
      <div>
        <header>
          <h2>Sesiones activas</h2>
          <ion-button size="small" fill="outline" onClick={() => this.cleanup()}>
            Limpiar expiradas
          </ion-button>
          <ion-toggle
            checked={this.activeOnly === 1}
            onIonChange={(e: any) => {
              this.activeOnly = e.detail.checked ? 1 : 0;
              this.refresh();
            }}
          >
            Solo activas
          </ion-toggle>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.sessions as unknown as Record<string, unknown>[]}
          searchKeys={['account_id', 'ip_address']}
          searchPlaceholder="Buscar cuenta o IP…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin sesiones.'}
        />
      </div>
    );
  }
}
