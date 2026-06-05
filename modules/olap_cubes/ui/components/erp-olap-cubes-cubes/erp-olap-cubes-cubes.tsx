import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles, SIEMPRE.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `olap_cubes` (Stencil). Mini-app: lista de definiciones de
// cubos OLAP + alta rápida. Es parte de la pieza `ui.entry` que el shell carga en runtime
// (modules/olap_cubes/dist/olap_cubes.esm.js).
//
// El componente NUNCA toca la BD: llama al SDK (erplora.query/command/on). El alta crea
// un cubo con una dimensión y una medida mínimas; la definición avanzada (varias dims/
// medidas, aggs, filtros) se edita desde un editor más rico (fuera de este MVP).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface OlapCube {
  id: string;
  code: string;
  name: string;
  description: string;
  source_table: string;
  dimensions: string;
  measures: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-olap-cubes-cubes',
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
export class ErpOlapCubesCubes {
  @State() cubes: OlapCube[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newCode = '';
  @State() newName = '';
  @State() newSource = '';
  @State() newDimension = '';
  @State() newMeasure = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'source_table', header: 'Tabla origen' },
    { key: 'dimensions', header: '# Dims', align: 'right', format: (r) => String(this.countJson(r.dimensions as string)) },
    { key: 'measures', header: '# Medidas', align: 'right', format: (r) => String(this.countJson(r.measures as string)) },
    { key: 'is_active', header: 'Activo', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('olap_cubes.cube.created', () => this.refresh());
      const off2 = erplora().on('olap_cubes.cube.updated', () => this.refresh());
      const off3 = erplora().on('olap_cubes.cube.deactivated', () => this.refresh());
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

  private countJson(raw: string): number {
    try {
      const v = JSON.parse(raw || '[]');
      return Array.isArray(v) ? v.length : 0;
    } catch {
      return 0;
    }
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const cubes = await erplora().query<OlapCube[]>('olap_cubes.cubes.list', { active_only: '1' });
      this.cubes = cubes ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando cubos';
    } finally {
      this.loading = false;
    }
  }

  private async createCube(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim() || !this.newSource.trim()) return;
    if (!this.newDimension.trim() || !this.newMeasure.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('olap_cubes.cubes.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        source_table: this.newSource.trim(),
        description: '',
        dimensions: [{ field: this.newDimension.trim(), label: this.newDimension.trim() }],
        measures: [{ field: this.newMeasure.trim(), label: this.newMeasure.trim(), agg: 'sum' }],
        filters: {},
      });
      this.newCode = '';
      this.newName = '';
      this.newSource = '';
      this.newDimension = '';
      this.newMeasure = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el cubo';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Cubos OLAP</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createCube(e)}>
          <ion-input placeholder="Código" value={this.newCode} onIonInput={(e: any) => (this.newCode = e.target.value)} />
          <ion-input placeholder="Nombre" value={this.newName} onIonInput={(e: any) => (this.newName = e.target.value)} />
          <ion-input placeholder="Tabla origen" value={this.newSource} onIonInput={(e: any) => (this.newSource = e.target.value)} />
          <ion-input placeholder="Dimensión (campo)" value={this.newDimension} onIonInput={(e: any) => (this.newDimension = e.target.value)} />
          <ion-input placeholder="Medida (campo)" value={this.newMeasure} onIonInput={(e: any) => (this.newMeasure = e.target.value)} />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCode || !this.newName || !this.newSource || !this.newDimension || !this.newMeasure}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.cubes as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'source_table']}
          searchPlaceholder="Buscar cubo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin cubos definidos.'}
        />
      </div>
    );
  }
}
