import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `locations` (vista bins). Mini-app: lista bins de una zona,
// alta rápida de bin, y bloquear/desbloquear. Parte de la pieza `ui.entry` que el shell
// carga en runtime (modules/locations/dist/locations.esm.js).
//
// La lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Warehouse {
  id: string;
  code: string;
  name: string;
  is_default: number;
}

interface Zone {
  id: string;
  code: string;
  name: string;
}

interface Bin {
  id: string;
  zone_id: string;
  warehouse_id: string;
  code: string;
  barcode: string;
  capacity: string | null;
  is_active: number;
  is_blocked: number;
  block_reason: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-locations-bins',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; flex-wrap:wrap; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpLocationsBins {
  @State() warehouses: Warehouse[] = [];
  @State() zones: Zone[] = [];
  @State() bins: Bin[] = [];
  @State() warehouseId = '';
  @State() zoneId = '';
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newBarcode = '';
  @State() newCapacity = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'barcode', header: 'Código de barras' },
    { key: 'capacity', header: 'Capacidad', align: 'right', format: (r) => (r.capacity == null ? '—' : String(r.capacity)) },
    { key: 'is_blocked', header: 'Estado', format: (r) => (r.is_blocked ? `Bloqueado (${r.block_reason || ''})` : 'OK') },
  ];

  private actions: DataTableAction[] = [
    { id: 'toggle_block', label: 'Bloquear/Desbloquear', icon: 'lock-closed-outline' },
  ];

  private onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    if (ev.detail.actionId === 'toggle_block') {
      this.toggleBlock(ev.detail.row as unknown as Bin);
    }
  }

  async componentWillLoad() {
    await this.loadWarehouses();
    try {
      const off1 = erplora().on('locations.bin.created', () => this.refreshBins());
      const off2 = erplora().on('locations.bin.blocked', () => this.refreshBins());
      const off3 = erplora().on('locations.bin.unblocked', () => this.refreshBins());
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

  private async loadWarehouses() {
    this.loading = true;
    this.error = '';
    try {
      const whs = await erplora().query<Warehouse[]>('locations.warehouses.list', { active_only: '1' });
      this.warehouses = whs ?? [];
      if (!this.warehouseId && this.warehouses.length) {
        const def = this.warehouses.find((w) => w.is_default) ?? this.warehouses[0];
        this.warehouseId = def.id;
      }
      await this.loadZones();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando almacenes';
    } finally {
      this.loading = false;
    }
  }

  private async loadZones() {
    if (!this.warehouseId) {
      this.zones = [];
      this.zoneId = '';
      this.bins = [];
      return;
    }
    try {
      const zs = await erplora().query<Zone[]>('locations.zones.list', {
        warehouse_id: this.warehouseId,
        zone_type: '',
      });
      this.zones = zs ?? [];
      if (this.zones.length && !this.zones.find((z) => z.id === this.zoneId)) {
        this.zoneId = this.zones[0].id;
      }
      await this.refreshBins();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando zonas';
    }
  }

  private async refreshBins() {
    this.error = '';
    try {
      const bs = await erplora().query<Bin[]>('locations.bins.list', {
        zone_id: this.zoneId || '',
        blocked_only: '',
      });
      this.bins = bs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando bins';
    }
  }

  private async onWarehouseChange(id: string) {
    this.warehouseId = id;
    await this.loadZones();
  }

  private async onZoneChange(id: string) {
    this.zoneId = id;
    await this.refreshBins();
  }

  private async createBin(ev: Event) {
    ev.preventDefault();
    if (!this.zoneId || !this.newCode.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('locations.bins.create', {
        zone_id: this.zoneId,
        code: this.newCode.trim(),
        barcode: this.newBarcode.trim(),
        capacity: this.newCapacity ? Number(this.newCapacity) : null,
      });
      this.newCode = '';
      this.newBarcode = '';
      this.newCapacity = '';
      await this.refreshBins();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el bin';
    } finally {
      this.saving = false;
    }
  }

  private async toggleBlock(b: Bin) {
    this.error = '';
    try {
      if (b.is_blocked) {
        await erplora().command('locations.bins.unblock', { bin_id: b.id });
      } else {
        const reason = (globalThis as any).prompt?.('Motivo del bloqueo:') ?? 'Bloqueado';
        if (!reason) return;
        await erplora().command('locations.bins.block', { bin_id: b.id, reason });
      }
      await this.refreshBins();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cambiar el estado';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Bins</h2>
          <ion-select
            placeholder="Almacén…"
            value={this.warehouseId}
            onIonChange={(e: any) => this.onWarehouseChange(e.target.value)}
          >
            {this.warehouses.map((w) => (
              <ion-select-option value={w.id} key={w.id}>
                {w.code} — {w.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Zona…"
            value={this.zoneId}
            onIonChange={(e: any) => this.onZoneChange(e.target.value)}
          >
            {this.zones.map((z) => (
              <ion-select-option value={z.id} key={z.id}>
                {z.code} — {z.name}
              </ion-select-option>
            ))}
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createBin(e)}>
          <ion-input
            placeholder="Código (A1-01)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Código de barras"
            value={this.newBarcode}
            onIonInput={(e: any) => (this.newBarcode = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Capacidad"
            value={this.newCapacity}
            onIonInput={(e: any) => (this.newCapacity = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.zoneId || !this.newCode}>
            {this.saving ? 'Guardando…' : 'Añadir bin'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.bins as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'barcode']}
          searchPlaceholder="Buscar bin…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin bins en esta zona.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
