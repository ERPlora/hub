import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_romania` (vista e-Transport). Mini-app: lista de
// avisos de transporte de mercancías (UIT) hacia ANAF + alta rápida de un borrador.
// Parte de la pieza `ui.entry` (dist/fiscal_romania.esm.js).
//
// La auto-numeración (ETR-...), la guarda de estado y la asignación del código UIT
// viven en Rust/WASM: este componente NO toca la BD; llama al SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ETransport {
  id: string;
  document_number: string;
  transport_type: string;
  origin_city: string;
  destination_city: string;
  vehicle_plate: string;
  departure_date: string | null;
  uit_code: string;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-romania-etransport',
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
export class ErpFiscalRomaniaEtransport {
  @State() docs: ETransport[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newType = 'national';
  @State() newOrigin = '';
  @State() newDestination = '';
  @State() newPlate = '';
  @State() newGoods = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Número' },
    { key: 'transport_type', header: 'Tipo' },
    { key: 'origin_city', header: 'Origen' },
    { key: 'destination_city', header: 'Destino' },
    { key: 'vehicle_plate', header: 'Matrícula' },
    { key: 'uit_code', header: 'UIT', format: (r) => (r.uit_code as string) || '—' },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fiscal_romania.etransport.created', () => this.refresh());
      const off2 = erplora().on('fiscal_romania.etransport.submitted', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
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
      const docs = await erplora().query<ETransport[]>('fiscal_romania.etransport.list', {
        status: this.statusFilter,
        limit: 100,
      });
      this.docs = docs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando avisos e-Transport';
    } finally {
      this.loading = false;
    }
  }

  private async createDoc(ev: Event) {
    ev.preventDefault();
    if (!this.newOrigin.trim() || !this.newDestination.trim() || !this.newPlate.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      // La descripción libre de mercancías se envía como una sola línea; el handler
      // WASM normaliza/valida la lista. La UI envía siempre un array no vacío.
      const goods = [{ description: this.newGoods.trim() || 'Mercancía', quantity: 1 }];
      await erplora().command('fiscal_romania.etransport.create', {
        transport_type: this.newType,
        origin_city: this.newOrigin.trim(),
        destination_city: this.newDestination.trim(),
        vehicle_plate: this.newPlate.trim().toUpperCase(),
        departure_date: null,
        goods,
      });
      this.newOrigin = '';
      this.newDestination = '';
      this.newPlate = '';
      this.newGoods = '';
      this.newType = 'national';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el aviso';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>e-Transport</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createDoc(e)}>
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="national">Nacional</ion-select-option>
            <ion-select-option value="intra_eu">Intra-UE</ion-select-option>
            <ion-select-option value="international">Internacional</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="Origen"
            value={this.newOrigin}
            onIonInput={(e: any) => (this.newOrigin = e.target.value)}
          />
          <ion-input
            placeholder="Destino"
            value={this.newDestination}
            onIonInput={(e: any) => (this.newDestination = e.target.value)}
          />
          <ion-input
            placeholder="Matrícula"
            value={this.newPlate}
            onIonInput={(e: any) => (this.newPlate = e.target.value)}
          />
          <ion-input
            placeholder="Mercancía"
            value={this.newGoods}
            onIonInput={(e: any) => (this.newGoods = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newOrigin || !this.newDestination || !this.newPlate}
          >
            {this.saving ? 'Guardando…' : 'Nuevo aviso'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.docs as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'origin_city', 'destination_city', 'vehicle_plate', 'status']}
          searchPlaceholder="Buscar número, ciudad, matrícula…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin avisos e-Transport.'}
        />
      </div>
    );
  }
}
