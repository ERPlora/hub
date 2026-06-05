import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `purchase_orders` (Stencil). Mini-app: directorio de
// proveedores + alta rápida. Es la segunda vista de navegación del módulo.
//
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El alta usa el comando SQL transaccional
// `purchase_orders.suppliers.create`. El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Supplier {
  id: string;
  name: string;
  tax_id: string;
  email: string;
  phone: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-purchase-orders-suppliers',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--ion-border-color,#e0ddd4); border-radius:8px; flex:1; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpPurchaseOrdersSuppliers {
  @State() suppliers: Supplier[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newTaxId = '';
  @State() newEmail = '';
  @State() newPhone = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'tax_id', header: 'NIF/CIF' },
    { key: 'email', header: 'Email' },
    { key: 'phone', header: 'Teléfono' },
    { key: 'is_active', header: 'Activo', align: 'center', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('purchase_orders.supplier.created', () => this.refresh());
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
      const rows = await erplora().query<Supplier[]>('purchase_orders.suppliers.list', {
        active_only: 0,
        search: '',
      });
      this.suppliers = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando proveedores';
    } finally {
      this.loading = false;
    }
  }

  private async createSupplier(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('purchase_orders.suppliers.create', {
        name: this.newName.trim(),
        tax_id: this.newTaxId.trim(),
        email: this.newEmail.trim(),
        phone: this.newPhone.trim(),
        address: '',
        notes: '',
      });
      this.newName = '';
      this.newTaxId = '';
      this.newEmail = '';
      this.newPhone = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el proveedor';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Proveedores</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createSupplier(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="NIF/CIF"
            value={this.newTaxId}
            onIonInput={(e: any) => (this.newTaxId = e.target.value)}
          />
          <ion-input
            type="email"
            placeholder="Email"
            value={this.newEmail}
            onIonInput={(e: any) => (this.newEmail = e.target.value)}
          />
          <ion-input
            placeholder="Teléfono"
            value={this.newPhone}
            onIonInput={(e: any) => (this.newPhone = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.suppliers as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'tax_id', 'email']}
          searchPlaceholder="Buscar proveedor…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin proveedores.'}
        />
      </div>
    );
  }
}
