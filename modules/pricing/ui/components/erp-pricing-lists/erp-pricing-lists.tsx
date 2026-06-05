import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `pricing` (Stencil). Mini-app: lista las listas de
// precios + reglas de descuento del hub, con alta rápida de lista de precios.
// Es la pieza `ui.entry` que el shell carga en runtime
// (modules/pricing/dist/pricing.esm.js).
//
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). Toda escritura la valida y ejecuta el runtime.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot,
// eligiendo HttpWsTransport en cloud o IpcTransport en Tauri). El listado usa
// el DataTable compartido + Ionic.
//
// El motor de precios (get_price = mejor precio por producto/cantidad/segmento)
// y el motor de descuentos (calculate_discount, reglas por prioridad) NO viven
// aquí ni en SQL: van a WASM Tier 2 (ver WASM-TODO.md). Esta vista es CRUD/lista.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface PriceList {
  id: string;
  code: string;
  name: string;
  currency: string;
  is_default: number;
  segment: string | null;
}

interface DiscountRule {
  id: string;
  code: string;
  name: string;
  rule_type: string;
  value: string;
  priority: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-pricing-lists',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    h3 { margin:1.5rem 0 .5rem; font-size:1rem; color:var(--muted,#5c594f); }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpPricingLists {
  @State() lists: PriceList[] = [];
  @State() rules: DiscountRule[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newCurrency = 'EUR';
  @State() saving = false;

  private unsub?: () => void;

  private listColumns: DataTableColumn[] = [
    {
      key: 'code',
      header: 'Código',
      format: (r) => `${r.code}${r.is_default ? '  (default)' : ''}`,
    },
    { key: 'name', header: 'Nombre' },
    { key: 'currency', header: 'Divisa' },
    { key: 'segment', header: 'Segmento', format: (r) => (r.segment as string) ?? '—' },
  ];

  private ruleColumns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'rule_type', header: 'Tipo' },
    { key: 'value', header: 'Valor', align: 'right' },
    { key: 'priority', header: 'Prioridad', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos cuando el runtime emite cambios de pricing.
    try {
      const off1 = erplora().on('pricing.price_list.created', () => this.refresh());
      const off2 = erplora().on('pricing.rule.created', () => this.refresh());
      const off3 = erplora().on('pricing.rule.deactivated', () => this.refresh());
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
      const [lists, rules] = await Promise.all([
        erplora().query<PriceList[]>('pricing.price_lists.list'),
        erplora().query<DiscountRule[]>('pricing.rules.list'),
      ]);
      this.lists = lists ?? [];
      this.rules = rules ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pricing';
    } finally {
      this.loading = false;
    }
  }

  private async createList(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    try {
      await erplora().command('pricing.price_lists.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        currency: (this.newCurrency || 'EUR').trim().toUpperCase(),
        segment: null,
        is_default: false,
        valid_from: null,
        valid_until: null,
      });
      this.newCode = '';
      this.newName = '';
      this.newCurrency = 'EUR';
      await this.refresh(); // (además del evento; garantiza refresco inmediato)
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la lista';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Listas de precios</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createList(e)}>
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
            placeholder="Divisa"
            value={this.newCurrency}
            onIonInput={(e: any) => (this.newCurrency = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.listColumns}
          rows={this.lists as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'currency']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin listas de precios.'}
        />

        <h3>Reglas de descuento</h3>
        <data-table
          columns={this.ruleColumns}
          rows={this.rules as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'rule_type']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin reglas de descuento.'}
        />
      </div>
    );
  }
}
