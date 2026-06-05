import { Component, State, h } from '@stencil/core';

// Web Component del módulo `online_booking` (Stencil): configuración (singleton por hub)
// de la página pública de reservas. Es la segunda vista que carga el shell vía ui.entry.
//
// El componente NO toca la BD: llama al SDK (erplora.query/command). El get-or-create del
// singleton con defaults vive en runtime — ver WASM-TODO.md; aquí, si la query devuelve
// vacío, se muestran los defaults del schema y el upsert crea la fila.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
}

interface Settings {
  is_enabled: number;
  page_title: string;
  welcome_message: string;
  primary_color: string;
  logo_url: string;
  require_phone: number;
  require_email: number;
  allow_staff_selection: number;
  allow_notes: number;
  min_advance_hours: number;
  max_advance_days: number;
  slot_duration_minutes: number;
  buffer_minutes: number;
  confirmation_message: string;
  cancellation_policy: string;
}

const DEFAULTS: Settings = {
  is_enabled: 0,
  page_title: 'Book an Appointment',
  welcome_message: '',
  primary_color: '#6366f1',
  logo_url: '',
  require_phone: 1,
  require_email: 1,
  allow_staff_selection: 1,
  allow_notes: 1,
  min_advance_hours: 2,
  max_advance_days: 30,
  slot_duration_minutes: 30,
  buffer_minutes: 0,
  confirmation_message: '',
  cancellation_policy: '',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-online-booking-settings',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(14rem,1fr)); gap:.75rem; margin-bottom:1rem; }
    .field { display:flex; flex-direction:column; gap:.25rem; }
    label { font-size:.85rem; color: var(--muted,#6b6557); }
    .row { display:flex; align-items:center; gap:.5rem; }
    .err { color:#d9480f; font-weight:600; }
    .ok { color:#2b8a3e; font-weight:600; }
    .actions { display:flex; gap:.5rem; margin-top:.5rem; }
  `,
})
export class ErpOnlineBookingSettings {
  @State() s: Settings = { ...DEFAULTS };
  @State() loading = true;
  @State() saving = false;
  @State() error = '';
  @State() saved = false;

  async componentWillLoad() {
    await this.refresh();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<Settings[]>('online_booking.settings.get');
      const row = Array.isArray(rows) ? rows[0] : (rows as unknown as Settings | undefined);
      this.s = row ? { ...DEFAULTS, ...row } : { ...DEFAULTS };
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando la configuración';
    } finally {
      this.loading = false;
    }
  }

  private set<K extends keyof Settings>(key: K, value: Settings[K]) {
    this.s = { ...this.s, [key]: value };
    this.saved = false;
  }

  private async save(ev: Event) {
    ev.preventDefault();
    this.saving = true;
    this.error = '';
    this.saved = false;
    try {
      await erplora().command('online_booking.settings.upsert', {
        is_enabled: !!this.s.is_enabled,
        page_title: this.s.page_title,
        welcome_message: this.s.welcome_message,
        primary_color: this.s.primary_color,
        logo_url: this.s.logo_url,
        require_phone: !!this.s.require_phone,
        require_email: !!this.s.require_email,
        allow_staff_selection: !!this.s.allow_staff_selection,
        allow_notes: !!this.s.allow_notes,
        min_advance_hours: Number(this.s.min_advance_hours) || 0,
        max_advance_days: Number(this.s.max_advance_days) || 1,
        slot_duration_minutes: Number(this.s.slot_duration_minutes) || 30,
        buffer_minutes: Number(this.s.buffer_minutes) || 0,
        confirmation_message: this.s.confirmation_message,
        cancellation_policy: this.s.cancellation_policy,
      });
      this.saved = true;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo guardar';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <form onSubmit={(e) => this.save(e)}>
        <header>
          <h2>Configuración de la página de reservas</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}
        {this.saved && <p class="ok">Configuración guardada.</p>}

        <div class="row" style={{ marginBottom: '1rem' }}>
          <ion-toggle
            checked={!!this.s.is_enabled}
            onIonChange={(e: any) => this.set('is_enabled', e.target.checked ? 1 : 0)}
          />
          <label>Página pública activada</label>
        </div>

        <div class="grid">
          <div class="field">
            <label>Título de la página</label>
            <ion-input
              value={this.s.page_title}
              onIonInput={(e: any) => this.set('page_title', e.target.value)}
            />
          </div>
          <div class="field">
            <label>Color primario</label>
            <ion-input
              value={this.s.primary_color}
              onIonInput={(e: any) => this.set('primary_color', e.target.value)}
            />
          </div>
          <div class="field">
            <label>URL del logo</label>
            <ion-input
              value={this.s.logo_url}
              onIonInput={(e: any) => this.set('logo_url', e.target.value)}
            />
          </div>
          <div class="field">
            <label>Antelación mínima (horas)</label>
            <ion-input
              type="number"
              min="0"
              max="168"
              value={String(this.s.min_advance_hours)}
              onIonInput={(e: any) => this.set('min_advance_hours', Number(e.target.value))}
            />
          </div>
          <div class="field">
            <label>Antelación máxima (días)</label>
            <ion-input
              type="number"
              min="1"
              max="365"
              value={String(this.s.max_advance_days)}
              onIonInput={(e: any) => this.set('max_advance_days', Number(e.target.value))}
            />
          </div>
          <div class="field">
            <label>Duración de slot (min)</label>
            <ion-input
              type="number"
              min="5"
              max="480"
              value={String(this.s.slot_duration_minutes)}
              onIonInput={(e: any) => this.set('slot_duration_minutes', Number(e.target.value))}
            />
          </div>
          <div class="field">
            <label>Buffer entre reservas (min)</label>
            <ion-input
              type="number"
              min="0"
              max="120"
              value={String(this.s.buffer_minutes)}
              onIonInput={(e: any) => this.set('buffer_minutes', Number(e.target.value))}
            />
          </div>
        </div>

        <div class="grid">
          <div class="row">
            <ion-toggle
              checked={!!this.s.require_phone}
              onIonChange={(e: any) => this.set('require_phone', e.target.checked ? 1 : 0)}
            />
            <label>Teléfono obligatorio</label>
          </div>
          <div class="row">
            <ion-toggle
              checked={!!this.s.require_email}
              onIonChange={(e: any) => this.set('require_email', e.target.checked ? 1 : 0)}
            />
            <label>Email obligatorio</label>
          </div>
          <div class="row">
            <ion-toggle
              checked={!!this.s.allow_staff_selection}
              onIonChange={(e: any) => this.set('allow_staff_selection', e.target.checked ? 1 : 0)}
            />
            <label>Permitir elegir personal</label>
          </div>
          <div class="row">
            <ion-toggle
              checked={!!this.s.allow_notes}
              onIonChange={(e: any) => this.set('allow_notes', e.target.checked ? 1 : 0)}
            />
            <label>Permitir notas</label>
          </div>
        </div>

        <div class="field">
          <label>Mensaje de bienvenida</label>
          <ion-textarea
            value={this.s.welcome_message}
            onIonInput={(e: any) => this.set('welcome_message', e.target.value)}
          />
        </div>
        <div class="field">
          <label>Mensaje de confirmación</label>
          <ion-textarea
            value={this.s.confirmation_message}
            onIonInput={(e: any) => this.set('confirmation_message', e.target.value)}
          />
        </div>
        <div class="field">
          <label>Política de cancelación</label>
          <ion-textarea
            value={this.s.cancellation_policy}
            onIonInput={(e: any) => this.set('cancellation_policy', e.target.value)}
          />
        </div>

        <div class="actions">
          <ion-button type="submit" disabled={this.saving || this.loading}>
            {this.saving ? 'Guardando…' : 'Guardar'}
          </ion-button>
        </div>
      </form>
    );
  }
}
