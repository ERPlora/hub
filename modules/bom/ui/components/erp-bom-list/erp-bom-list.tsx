import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `bom` (Stencil). Mini-app: lista de BOMs (recetas) con
// filtros + alta rápida en draft. Es la pieza `ui.entry` que el shell carga en
// runtime (modules/bom/dist/bom.esm.js).
//
// La lógica de cálculo (explosionado multinivel, set_default, clone) vive en WASM:
// este componente NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Bom {
  id: string;
  code: string;
  name: string;
  product_ref: string;
  version: string;
  status: string;
  is_default: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-bom-list',
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
export class ErpBomList {
  @State() boms: Bom[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newProduct = '';
  @State() newVersion = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'product_ref', header: 'Producto' },
    { key: 'version', header: 'Versión' },
    { key: 'status', header: 'Estado' },
    { key: 'is_default', header: 'Default', align: 'center', format: (r) => (r.is_default ? '★' : '') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('bom.bom.created', () => this.refresh());
      const off2 = erplora().on('bom.bom.approved', () => this.refresh());
      const off3 = erplora().on('bom.bom.obsoleted', () => this.refresh());
      const off4 = erplora().on('bom.bom.default_changed', () => this.refresh());
      const off5 = erplora().on('bom.bom.cloned', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
        off5();
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
      const boms = await erplora().query<Bom[]>('bom.boms.list', {
        product_ref: '',
        status: this.statusFilter,
      });
      this.boms = boms ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando BOMs';
    } finally {
      this.loading = false;
    }
  }

  private async createBom(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim() || !this.newProduct.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('bom.boms.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        product_ref: this.newProduct.trim(),
        version: this.newVersion.trim() || '1.0',
        notes: '',
      });
      this.newCode = '';
      this.newName = '';
      this.newProduct = '';
      this.newVersion = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la BOM';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Listas de materiales (BOM)</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createBom(e)}>
          <ion-input
            placeholder="Código"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Producto (ref)"
            value={this.newProduct}
            onIonInput={(e: any) => (this.newProduct = e.target.value)}
          />
          <ion-input
            placeholder="Versión (1.0)"
            value={this.newVersion}
            onIonInput={(e: any) => (this.newVersion = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCode || !this.newName || !this.newProduct}
          >
            {this.saving ? 'Guardando…' : 'Nueva BOM'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.boms as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'product_ref']}
          searchPlaceholder="Buscar código, nombre o producto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin BOMs.'}
        />
      </div>
    );
  }
}
