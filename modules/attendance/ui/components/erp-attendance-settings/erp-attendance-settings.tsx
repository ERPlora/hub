import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `attendance` (Stencil). Vista de configuración (singleton
// por hub): foto obligatoria, entrada manual, umbral de retraso/salida anticipada y
// auto-cierre. Carga vía erplora.query y guarda vía erplora.command. El WC NUNCA toca
// la BD. Muestra los valores actuales en un <data-table> de sólo lectura.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AttendanceSettings {
  require_photo: number;
  allow_manual_entry: number;
  late_threshold_minutes: number;
  early_departure_minutes: number;
  auto_clock_out_hours: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const DEFAULTS: AttendanceSettings = {
  require_photo: 0,
  allow_manual_entry: 1,
  late_threshold_minutes: 15,
  early_departure_minutes: 15,
  auto_clock_out_hours: 12,
};

@Component({
  tag: 'erp-attendance-settings',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.75rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .row { display:flex; gap:.5rem; align-items:center; }
    .err { color:#d9480f; font-weight:600; }
    .ok { color:#2b8a3e; font-weight:600; }
  `,
})
export class ErpAttendanceSettings {
  @State() settings: AttendanceSettings = { ...DEFAULTS };
  @State() loading = true;
  @State() saving = false;
  @State() error = '';
  @State() saved = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'label', header: 'Ajuste' },
    { key: 'value', header: 'Valor actual', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('attendance.settings.updated', () => this.refresh());
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
      const rows = await erplora().query<AttendanceSettings[]>('attendance.settings.get');
      this.settings = rows && rows.length ? rows[0] : { ...DEFAULTS };
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando configuración';
    } finally {
      this.loading = false;
    }
  }

  private async save(ev: Event) {
    ev.preventDefault();
    this.saving = true;
    this.error = '';
    this.saved = false;
    try {
      await erplora().command('attendance.settings.update', {
        require_photo: !!this.settings.require_photo,
        allow_manual_entry: !!this.settings.allow_manual_entry,
        late_threshold_minutes: Number(this.settings.late_threshold_minutes) || 0,
        early_departure_minutes: Number(this.settings.early_departure_minutes) || 0,
        auto_clock_out_hours: Number(this.settings.auto_clock_out_hours) || 0,
      });
      this.saved = true;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo guardar la configuración';
    } finally {
      this.saving = false;
    }
  }

  private get summaryRows(): Record<string, unknown>[] {
    const s = this.settings;
    return [
      { id: 'require_photo', label: 'Foto obligatoria', value: s.require_photo ? 'Sí' : 'No' },
      { id: 'allow_manual_entry', label: 'Entrada manual', value: s.allow_manual_entry ? 'Sí' : 'No' },
      { id: 'late', label: 'Umbral de retraso (min)', value: String(s.late_threshold_minutes) },
      { id: 'early', label: 'Salida anticipada (min)', value: String(s.early_departure_minutes) },
      { id: 'auto', label: 'Auto-cierre (horas)', value: String(s.auto_clock_out_hours) },
    ];
  }

  render() {
    return (
      <div>
        <header>
          <h2>Configuración de fichajes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.save(e)}>
          <ion-input
            type="number"
            label="Umbral retraso (min)"
            labelPlacement="stacked"
            value={String(this.settings.late_threshold_minutes)}
            onIonInput={(e: any) => (this.settings = { ...this.settings, late_threshold_minutes: e.target.value })}
          />
          <ion-input
            type="number"
            label="Salida anticipada (min)"
            labelPlacement="stacked"
            value={String(this.settings.early_departure_minutes)}
            onIonInput={(e: any) => (this.settings = { ...this.settings, early_departure_minutes: e.target.value })}
          />
          <ion-input
            type="number"
            label="Auto-cierre (horas)"
            labelPlacement="stacked"
            value={String(this.settings.auto_clock_out_hours)}
            onIonInput={(e: any) => (this.settings = { ...this.settings, auto_clock_out_hours: e.target.value })}
          />
          <div class="row">
            <ion-toggle
              checked={!!this.settings.require_photo}
              onIonChange={(e: any) => (this.settings = { ...this.settings, require_photo: e.target.checked ? 1 : 0 })}
            >
              Foto obligatoria
            </ion-toggle>
          </div>
          <div class="row">
            <ion-toggle
              checked={!!this.settings.allow_manual_entry}
              onIonChange={(e: any) => (this.settings = { ...this.settings, allow_manual_entry: e.target.checked ? 1 : 0 })}
            >
              Entrada manual
            </ion-toggle>
          </div>
          <ion-button type="submit" size="small" disabled={this.saving}>
            {this.saving ? 'Guardando…' : 'Guardar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}
        {this.saved && <p class="ok">Configuración guardada.</p>}

        <data-table
          columns={this.columns}
          rows={this.summaryRows}
          searchKeys={[]}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin configuración.'}
        />
      </div>
    );
  }
}
