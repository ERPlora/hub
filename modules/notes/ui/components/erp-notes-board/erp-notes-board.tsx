import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `notes` (Stencil). Es la pieza `ui.entry` que el shell
// carga en runtime (modules/notes/dist/notes.esm.js).
//
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). Toda escritura la valida y ejecuta el runtime.
// El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Note {
  id: string;
  title: string;
  body: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-notes-board',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b17); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--ion-border-color,#e7e2d6); border-radius:8px; min-width:8rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpNotesBoard {
  @State() notes: Note[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newTitle = '';
  @State() newBody = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'title', header: 'Título' },
    { key: 'body', header: 'Detalle' },
    { key: 'created_at', header: 'Creada', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: cuando el runtime emite que se creó una nota, recargamos.
    try {
      this.unsub = erplora().on('notes.created', () => this.refresh());
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
      const rows = await erplora().query<Note[]>('notes.list');
      this.notes = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando notas';
    } finally {
      this.loading = false;
    }
  }

  private async createNote(ev: Event) {
    ev.preventDefault();
    if (!this.newTitle.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('notes.create', {
        title: this.newTitle.trim(),
        body: this.newBody.trim(),
      });
      this.newTitle = '';
      this.newBody = '';
      await this.refresh(); // además del evento; garantiza refresco inmediato
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la nota';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Notas</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createNote(e)}>
          <ion-input
            placeholder="Título"
            value={this.newTitle}
            onIonInput={(e: any) => (this.newTitle = e.target.value)}
          />
          <ion-input
            placeholder="Detalle"
            value={this.newBody}
            onIonInput={(e: any) => (this.newBody = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newTitle.trim()}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.notes as unknown as Record<string, unknown>[]}
          searchKeys={['title', 'body']}
          searchPlaceholder="Buscar nota…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin notas.'}
        />
      </div>
    );
  }
}
