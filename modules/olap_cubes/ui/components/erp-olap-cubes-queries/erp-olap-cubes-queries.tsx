import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles, SIEMPRE.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `olap_cubes` (Stencil). Mini-app: historial de ejecuciones de
// consultas OLAP (auditoría / re-ejecución). Es parte de la pieza `ui.entry` que el shell
// carga en runtime (modules/olap_cubes/dist/olap_cubes.esm.js).
//
// El componente NUNCA toca la BD: llama al SDK (erplora.query/command/on). La ejecución de
// una query es lógica de agregación (handler WASM olap_cubes.query.execute) y se dispara
// desde un editor de consultas más rico; aquí solo listamos el histórico.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface OlapQuery {
  id: string;
  cube_id: string;
  query_number: string;
  dimensions_used: string;
  measures_used: string;
  result_count: number;
  executed_at: string | null;
  execution_time_ms: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-olap-cubes-queries',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpOlapCubesQueries {
  @State() queries: OlapQuery[] = [];
  @State() loading = true;
  @State() error = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'query_number', header: 'Nº consulta' },
    { key: 'dimensions_used', header: 'Dimensiones', format: (r) => this.joinJson(r.dimensions_used as string) },
    { key: 'measures_used', header: 'Medidas', format: (r) => this.joinJson(r.measures_used as string) },
    { key: 'result_count', header: 'Filas', align: 'right' },
    { key: 'execution_time_ms', header: 'ms', align: 'right' },
    { key: 'executed_at', header: 'Ejecutada' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('olap_cubes.query.executed', () => this.refresh());
      this.unsub = off;
    } catch {
      /* sin SDK (preview) → sin reactividad en vivo */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private joinJson(raw: string): string {
    try {
      const v = JSON.parse(raw || '[]');
      return Array.isArray(v) ? v.join(', ') : '';
    } catch {
      return '';
    }
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const queries = await erplora().query<OlapQuery[]>('olap_cubes.queries.list', { cube_id: '' });
      this.queries = queries ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando consultas';
    } finally {
      this.loading = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Consultas OLAP</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.queries as unknown as Record<string, unknown>[]}
          searchKeys={['query_number']}
          searchPlaceholder="Buscar nº de consulta…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin consultas ejecutadas.'}
        />
      </div>
    );
  }
}
