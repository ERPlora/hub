import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `email_marketing` (Stencil). Vista de listas: muestra las
// listas de destinatarios del hub + alta rápida. NO toca la BD: todo va por el SDK
// (erplora.query/command/on). El contador total_subscribers lo mantiene el WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface EmailList {
  id: string;
  name: string;
  description: string;
  is_active: number;
  total_subscribers: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-email-marketing-lists',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpEmailMarketingLists {
  @State() lists: EmailList[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newDescription = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'description', header: 'Descripción' },
    { key: 'total_subscribers', header: 'Suscriptores', align: 'right' },
    { key: 'is_active', header: 'Activa', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('email_marketing.list.created', () => this.refresh());
      const off2 = erplora().on('email_marketing.subscriber.subscribed', () => this.refresh());
      const off3 = erplora().on('email_marketing.subscriber.unsubscribed', () => this.refresh());
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
      const lists = await erplora().query<EmailList[]>('email_marketing.lists.list', { active_only: 0 });
      this.lists = lists ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando listas';
    } finally {
      this.loading = false;
    }
  }

  private async createList(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('email_marketing.lists.create', {
        name: this.newName.trim(),
        description: this.newDescription.trim(),
      });
      this.newName = '';
      this.newDescription = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la lista';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Listas de destinatarios</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createList(e)}>
          <ion-input
            placeholder="Nombre de la lista"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Descripción (opcional)"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Crear lista'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.lists as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'description']}
          searchPlaceholder="Buscar lista…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin listas.'}
        />
      </div>
    );
  }
}
