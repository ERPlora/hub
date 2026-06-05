import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `expenses` (Stencil). Vista de categorías de gasto
// (jerárquicas vía parent_id) + alta rápida. El WC NUNCA toca la BD: lee con
// erplora.query y crea con erplora.command.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ExpenseCategory {
  id: string;
  code: string;
  name: string;
  description: string;
  parent_id: string | null;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-expenses-categories',
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
export class ErpExpensesCategories {
  @State() categories: ExpenseCategory[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newCode = '';
  @State() newName = '';
  @State() newParent = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'parent_id', header: 'Padre', format: (r) => this.catName(r.parent_id as string | null) },
    { key: 'description', header: 'Descripción' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('expenses.category.created', () => this.refresh());
      this.unsub = () => off();
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
      const cats = await erplora().query<ExpenseCategory[]>('expenses.categories.list');
      this.categories = cats ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando categorías';
    } finally {
      this.loading = false;
    }
  }

  private async createCategory(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('expenses.categories.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        parent_id: this.newParent || null,
        description: '',
      });
      this.newCode = '';
      this.newName = '';
      this.newParent = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la categoría';
    } finally {
      this.saving = false;
    }
  }

  private catName(id: string | null): string {
    if (!id) return '—';
    return this.categories.find((c) => c.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Categorías de gasto</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createCategory(e)}>
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
          <ion-select
            placeholder="Categoría padre (opcional)…"
            value={this.newParent}
            onIonChange={(e: any) => (this.newParent = e.target.value)}
          >
            <ion-select-option value="">— Sin padre —</ion-select-option>
            {this.categories.map((c) => (
              <ion-select-option value={c.id} key={c.id}>
                {c.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCode || !this.newName}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.categories as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name']}
          searchPlaceholder="Buscar categoría…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin categorías.'}
        />
      </div>
    );
  }
}
