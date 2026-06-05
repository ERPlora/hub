import { Component, State, h } from '@stencil/core';
// DataTable compartido (efecto secundario: auto-registro + bundling). No se usa una
// tabla aquí (es un formulario), pero se importa para mantener el contrato de bundling
// del módulo consistente con el resto de vistas.
import '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `verifactu`: formulario de configuración (singleton por hub).
// Carga la config vía erplora.query y la guarda vía erplora.command. El WC NO toca la BD.
// El certificado se cifra en el runtime (capacidad de host); aquí solo se envía en claro.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface VerifactuConfig {
  id?: string;
  enabled?: boolean;
  mode?: string;
  environment?: string;
  software_name?: string;
  software_version?: string;
  software_id?: string;
  software_nif?: string;
  certificate_path?: string;
  auto_transmit?: boolean;
  retry_interval_minutes?: number;
  max_retries?: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-verifactu-settings',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; flex-direction:column; gap:.6rem; max-width:32rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; }
    .row { display:flex; gap:.5rem; align-items:center; }
    label { font-size:.85rem; color:var(--muted,#8b897f); }
    .err { color:#d9480f; font-weight:600; }
    .ok { color:#2b8a3e; font-weight:600; }
  `,
})
export class ErpVerifactuSettings {
  @State() cfg: VerifactuConfig = {};
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
      const c = await erplora().query<VerifactuConfig | null>('verifactu.config.get');
      this.cfg = c ?? {};
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando la configuración';
    } finally {
      this.loading = false;
    }
  }

  private set<K extends keyof VerifactuConfig>(key: K, value: VerifactuConfig[K]) {
    this.cfg = { ...this.cfg, [key]: value };
    this.saved = false;
  }

  private async save(ev: Event) {
    ev.preventDefault();
    this.saving = true;
    this.error = '';
    this.saved = false;
    try {
      await erplora().command('verifactu.config.save', {
        enabled: !!this.cfg.enabled,
        mode: this.cfg.mode || 'verifactu',
        environment: this.cfg.environment || 'testing',
        software_name: this.cfg.software_name || 'ERPlora Hub',
        software_version: this.cfg.software_version || '1.0.0',
        software_id: this.cfg.software_id || 'ERPLORA-001',
        software_nif: this.cfg.software_nif || '',
        certificate_path: this.cfg.certificate_path || '',
        certificate_password: '',
        certificate_expiry: null,
        auto_transmit: this.cfg.auto_transmit !== false,
        retry_interval_minutes: Number(this.cfg.retry_interval_minutes) || 5,
        max_retries: Number(this.cfg.max_retries) || 10,
      });
      this.saved = true;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo guardar la configuración';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Configuración VeriFactu</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}
        {this.saved && <p class="ok">Configuración guardada correctamente.</p>}

        <form class="form" onSubmit={(e) => this.save(e)}>
          <div class="row">
            <ion-checkbox
              checked={!!this.cfg.enabled}
              onIonChange={(e: any) => this.set('enabled', e.target.checked)}
            />
            <label>Activar VeriFactu</label>
          </div>

          <label>Entorno AEAT</label>
          <ion-select
            value={this.cfg.environment || 'testing'}
            onIonChange={(e: any) => this.set('environment', e.target.value)}
          >
            <ion-select-option value="testing">Pruebas (AEAT Test)</ion-select-option>
            <ion-select-option value="production">Producción</ion-select-option>
          </ion-select>

          <label>NIF del software / emisor</label>
          <ion-input
            value={this.cfg.software_nif || ''}
            placeholder="B12345678"
            onIonInput={(e: any) => this.set('software_nif', e.target.value)}
          />

          <label>Nombre del software</label>
          <ion-input
            value={this.cfg.software_name || ''}
            placeholder="ERPlora Hub"
            onIonInput={(e: any) => this.set('software_name', e.target.value)}
          />

          <label>ID del software</label>
          <ion-input
            value={this.cfg.software_id || ''}
            placeholder="ERPLORA-001"
            onIonInput={(e: any) => this.set('software_id', e.target.value)}
          />

          <label>Versión del software</label>
          <ion-input
            value={this.cfg.software_version || ''}
            placeholder="1.0.0"
            onIonInput={(e: any) => this.set('software_version', e.target.value)}
          />

          <label>Ruta del certificado (.p12)</label>
          <ion-input
            value={this.cfg.certificate_path || ''}
            placeholder="/ruta/al/certificado.p12"
            onIonInput={(e: any) => this.set('certificate_path', e.target.value)}
          />

          <div class="row">
            <ion-checkbox
              checked={this.cfg.auto_transmit !== false}
              onIonChange={(e: any) => this.set('auto_transmit', e.target.checked)}
            />
            <label>Transmisión automática a AEAT</label>
          </div>

          <ion-button type="submit" disabled={this.saving || this.loading}>
            {this.saving ? 'Guardando…' : 'Guardar configuración'}
          </ion-button>
        </form>
      </div>
    );
  }
}
