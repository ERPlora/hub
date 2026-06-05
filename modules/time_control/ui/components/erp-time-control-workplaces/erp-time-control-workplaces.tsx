import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `time_control` (Stencil). Mini-app: lista de centros de
// trabajo (workplaces) para geofencing + alta rápida. El WC NO toca la BD; llama al
// SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Workplace {
  id: string;
  name: string;
  address: string;
  latitude: string | null;
  longitude: string | null;
  radius_meters: number;
  is_active: number;
  is_default: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-time-control-workplaces',
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
export class ErpTimeControlWorkplaces {
  @State() workplaces: Workplace[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;

  @State() newName = '';
  @State() newAddress = '';
  @State() newLat = '';
  @State() newLon = '';
  @State() newRadius = '100';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'address', header: 'Dirección' },
    { key: 'radius_meters', header: 'Radio (m)', align: 'right' },
    {
      key: 'latitude',
      header: 'Coordenadas',
      format: (r) =>
        r.latitude && r.longitude ? `${r.latitude}, ${r.longitude}` : '—',
    },
    { key: 'is_default', header: 'Por defecto', format: (r) => (r.is_default ? 'Sí' : '') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('time_control.workplace.created', () => this.refresh());
      const off2 = erplora().on('time_control.workplace.updated', () => this.refresh());
      const off3 = erplora().on('time_control.workplace.deleted', () => this.refresh());
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
      const workplaces = await erplora().query<Workplace[]>('time_control.workplaces.list');
      this.workplaces = workplaces ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando centros de trabajo';
    } finally {
      this.loading = false;
    }
  }

  private async createWorkplace(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('time_control.workplaces.create', {
        name: this.newName.trim(),
        address: this.newAddress.trim(),
        latitude: this.newLat.trim() ? Number(this.newLat) : null,
        longitude: this.newLon.trim() ? Number(this.newLon) : null,
        radius_meters: Number(this.newRadius) || 100,
        is_default: false,
      });
      this.newName = '';
      this.newAddress = '';
      this.newLat = '';
      this.newLon = '';
      this.newRadius = '100';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el centro de trabajo';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Centros de trabajo</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createWorkplace(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Dirección"
            value={this.newAddress}
            onIonInput={(e: any) => (this.newAddress = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.0000001"
            placeholder="Latitud"
            value={this.newLat}
            onIonInput={(e: any) => (this.newLat = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.0000001"
            placeholder="Longitud"
            value={this.newLon}
            onIonInput={(e: any) => (this.newLon = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Radio (m)"
            value={this.newRadius}
            onIonInput={(e: any) => (this.newRadius = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.workplaces as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'address']}
          searchPlaceholder="Buscar centro…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin centros de trabajo.'}
        />
      </div>
    );
  }
}
