import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `training` (Stencil). Mini-app: lista de programas de
// formación + alta rápida. Es una de las piezas que el shell carga vía `ui.entry`
// (modules/training/dist/training.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TrainingProgram {
  id: string;
  name: string;
  description: string;
  duration_hours: number;
  is_mandatory: number;
  category: string | null;
  provider: string | null;
  cost: string;
  max_participants: number;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-training-programs',
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
export class ErpTrainingPrograms {
  @State() programs: TrainingProgram[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newCategory = '';
  @State() newProvider = '';
  @State() newHours = '';
  @State() newCost = '';
  @State() newMandatory = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Programa' },
    { key: 'category', header: 'Categoría', format: (r) => (r.category as string) ?? '—' },
    { key: 'provider', header: 'Proveedor', format: (r) => (r.provider as string) ?? '—' },
    { key: 'duration_hours', header: 'Horas', align: 'right' },
    { key: 'cost', header: 'Coste', align: 'right', format: (r) => Number(r.cost).toFixed(2) },
    { key: 'is_mandatory', header: 'Obligatorio', format: (r) => (r.is_mandatory ? 'Sí' : 'No') },
    { key: 'is_active', header: 'Activo', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('training.program.created', () => this.refresh());
      const off2 = erplora().on('training.program.updated', () => this.refresh());
      const off3 = erplora().on('training.program.deleted', () => this.refresh());
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
      const rows = await erplora().query<TrainingProgram[]>('training.programs.list', {
        search: '',
        category: '',
        is_mandatory: -1,
        is_active: -1,
      });
      this.programs = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando programas';
    } finally {
      this.loading = false;
    }
  }

  private async createProgram(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('training.programs.create', {
        name: this.newName.trim(),
        description: '',
        duration_hours: Number(this.newHours) || 0,
        is_mandatory: this.newMandatory ? 1 : 0,
        category: this.newCategory.trim() || null,
        provider: this.newProvider.trim() || null,
        cost: Number(this.newCost) || 0,
        max_participants: 0,
      });
      this.newName = '';
      this.newCategory = '';
      this.newProvider = '';
      this.newHours = '';
      this.newCost = '';
      this.newMandatory = false;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el programa';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Programas de formación</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createProgram(e)}>
          <ion-input
            placeholder="Nombre del programa"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Categoría"
            value={this.newCategory}
            onIonInput={(e: any) => (this.newCategory = e.target.value)}
          />
          <ion-input
            placeholder="Proveedor"
            value={this.newProvider}
            onIonInput={(e: any) => (this.newProvider = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Horas"
            value={this.newHours}
            onIonInput={(e: any) => (this.newHours = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Coste"
            value={this.newCost}
            onIonInput={(e: any) => (this.newCost = e.target.value)}
          />
          <ion-select
            placeholder="¿Obligatorio?"
            value={this.newMandatory ? '1' : '0'}
            onIonChange={(e: any) => (this.newMandatory = e.target.value === '1')}
          >
            <ion-select-option value="0">Opcional</ion-select-option>
            <ion-select-option value="1">Obligatorio</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.programs as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'category', 'provider']}
          searchPlaceholder="Buscar programa…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin programas de formación.'}
        />
      </div>
    );
  }
}
