import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `online_store` (Stencil). Vista: páginas CMS del escaparate
// (about, condiciones…) + alta rápida. Segunda pieza del bundle `ui.entry`.
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). El listado usa
// el DataTable compartido + Ionic. Acción por fila (publicar) → rowAction.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface StorePage {
  id: string;
  slug: string;
  title: string;
  is_published: number;
  order_in_menu: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-online-store-pages',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-textarea { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpOnlineStorePages {
  @State() pages: StorePage[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newSlug = '';
  @State() newTitle = '';
  @State() newContent = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'title', header: 'Título' },
    { key: 'slug', header: 'Slug' },
    { key: 'order_in_menu', header: 'Orden', align: 'right' },
    { key: 'is_published', header: 'Estado', format: (r) => (Number(r.is_published) ? 'Publicada' : 'Borrador') },
  ];

  private actions: DataTableAction[] = [{ id: 'publish', label: 'Publicar', icon: 'eye-outline', color: 'success' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('online_store.page.created', () => this.refresh()),
        erplora().on('online_store.page.published', () => this.refresh()),
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
      const pages = await erplora().query<StorePage[]>('online_store.pages.list', { is_published: -1 });
      this.pages = pages ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando páginas';
    } finally {
      this.loading = false;
    }
  }

  private async createPage(ev: Event) {
    ev.preventDefault();
    if (!this.newSlug.trim() || !this.newTitle.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('online_store.pages.create', {
        slug: this.newSlug.trim(),
        title: this.newTitle.trim(),
        content_html: this.newContent,
      });
      this.newSlug = '';
      this.newTitle = '';
      this.newContent = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la página';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId !== 'publish') return;
    this.error = '';
    try {
      await erplora().command('online_store.pages.publish', { page_id: String(row.id) });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo publicar la página';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Páginas del escaparate</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createPage(e)}>
          <ion-input
            placeholder="Título"
            value={this.newTitle}
            onIonInput={(e: any) => (this.newTitle = e.target.value)}
          />
          <ion-input
            placeholder="Slug (sobre-nosotros)"
            value={this.newSlug}
            onIonInput={(e: any) => (this.newSlug = e.target.value)}
          />
          <ion-textarea
            placeholder="Contenido HTML"
            value={this.newContent}
            onIonInput={(e: any) => (this.newContent = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newTitle || !this.newSlug}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.pages as unknown as Record<string, unknown>[]}
          searchKeys={['title', 'slug']}
          searchPlaceholder="Buscar título o slug…"
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin páginas CMS.'}
        />
      </div>
    );
  }
}
