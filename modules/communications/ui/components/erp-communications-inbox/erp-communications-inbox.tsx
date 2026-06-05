import { Component, State, h } from '@stencil/core';
import type { DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `communications` (Stencil). Mini-app: inbox unificado
// de hilos (email/chat/DM) por carpeta + acciones simples de estado/carpeta.
// Es la pieza `ui.entry` que el shell carga en runtime
// (modules/communications/dist/communications.esm.js).
//
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El envío/compose real va por handler WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Thread {
  id: string;
  subject: string;
  contact_name: string;
  contact_identifier: string;
  status: string;
  priority: string;
  folder: string;
  unread_count: number;
  message_count: number;
  last_message_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-communications-inbox',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCommunicationsInbox {
  @State() threads: Thread[] = [];
  @State() loading = true;
  @State() error = '';
  @State() folder = 'inbox';
  @State() unreadOnly = 0;
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'contact_name', header: 'Contacto', format: (r) => (r.contact_name as string) || (r.contact_identifier as string) || '—' },
    { key: 'subject', header: 'Asunto', format: (r) => (r.subject as string) || '(sin asunto)' },
    { key: 'status', header: 'Estado' },
    { key: 'priority', header: 'Prioridad' },
    { key: 'unread_count', header: 'No leídos', align: 'right' },
    { key: 'last_message_at', header: 'Último', format: (r) => (r.last_message_at ? String(r.last_message_at).slice(0, 16) : '—') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('communications.thread.status_changed', () => this.refresh());
      const off2 = erplora().on('communications.account.created', () => this.refresh());
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
      const threads = await erplora().query<Thread[]>('communications.threads.list', {
        folder: this.folder,
        status: '',
        unread_only: this.unreadOnly,
      });
      this.threads = threads ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando el inbox';
    } finally {
      this.loading = false;
    }
  }

  private actions: DataTableAction[] = [{ id: 'archive', label: 'Archivar', icon: 'archive-outline' }];

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    if (ev.detail.actionId === 'archive') this.archive(ev.detail.row);
  };

  private async archive(row: Record<string, unknown>) {
    const id = row.id as string;
    if (!id) return;
    this.busyId = id;
    this.error = '';
    try {
      await erplora().command('communications.threads.set_status', {
        id,
        status: 'archived',
        folder: 'archive',
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo archivar el hilo';
    } finally {
      this.busyId = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Inbox</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Carpeta…"
            value={this.folder}
            onIonChange={(e: any) => {
              this.folder = e.target.value;
              this.refresh();
            }}
          >
            {['inbox', 'sent', 'drafts', 'archive', 'spam', 'trash'].map((f) => (
              <ion-select-option value={f} key={f}>
                {f}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Filtro…"
            value={String(this.unreadOnly)}
            onIonChange={(e: any) => {
              this.unreadOnly = Number(e.target.value) || 0;
              this.refresh();
            }}
          >
            <ion-select-option value="0">Todos</ion-select-option>
            <ion-select-option value="1">Solo no leídos</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.threads as unknown as Record<string, unknown>[]}
          searchKeys={['contact_name', 'contact_identifier', 'subject']}
          searchPlaceholder="Buscar contacto o asunto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin conversaciones en esta carpeta.'}
          actions={this.actions}
          onRowAction={this.onRowAction}
        />
      </div>
    );
  }
}
