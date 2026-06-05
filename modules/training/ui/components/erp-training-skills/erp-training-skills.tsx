import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `training` (Stencil). Mini-app: catálogo de habilidades
// + alta rápida. Segunda pieza del bundle `ui.entry` (training.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Skill {
  id: string;
  name: string;
  category: string | null;
  description: string | null;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-training-skills',
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
export class ErpTrainingSkills {
  @State() skills: Skill[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newCategory = '';
  @State() newDescription = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Habilidad' },
    { key: 'category', header: 'Categoría', format: (r) => (r.category as string) ?? '—' },
    { key: 'description', header: 'Descripción', format: (r) => (r.description as string) ?? '—' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('training.skill.created', () => this.refresh());
      const off2 = erplora().on('training.skill.updated', () => this.refresh());
      const off3 = erplora().on('training.skill.deleted', () => this.refresh());
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
      const rows = await erplora().query<Skill[]>('training.skills.list', {
        search: '',
        category: '',
      });
      this.skills = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando habilidades';
    } finally {
      this.loading = false;
    }
  }

  private async createSkill(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('training.skills.create', {
        name: this.newName.trim(),
        category: this.newCategory.trim() || null,
        description: this.newDescription.trim() || null,
      });
      this.newName = '';
      this.newCategory = '';
      this.newDescription = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la habilidad';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Habilidades</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createSkill(e)}>
          <ion-input
            placeholder="Nombre de la habilidad"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Categoría"
            value={this.newCategory}
            onIonInput={(e: any) => (this.newCategory = e.target.value)}
          />
          <ion-input
            placeholder="Descripción"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.skills as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'category']}
          searchPlaceholder="Buscar habilidad…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin habilidades.'}
        />
      </div>
    );
  }
}
