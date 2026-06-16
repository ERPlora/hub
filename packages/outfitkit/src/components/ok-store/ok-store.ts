import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import { createStore, type Store } from '../../store/store.js';

// ok-store — elemento declarativo para usar el store reactivo SIN escribir JS (p.ej. en plantillas
// Django). No renderiza UI: deja pasar su contenido por un slot default (display:contents) y posee
// un `store` con el `name` indicado. Expone la instancia como propiedad `.store` y métodos proxy
// `get/set/updateValue/delete` (`updateValue` porque `update` lo reserva LitElement). Emite:
//   - `ok-store-change` { key, value } en CADA cambio del store.
//   - `ok-store-ready`  cuando `store.ready` resuelve (caché hidratada desde IndexedDB).
//
// Ejemplo (Django): un contador que persiste entre recargas:
//   <ok-store name="demo" id="s"></ok-store>
//   <button onclick="s.set('count', (s.get('count')||0)+1)">+1</button>
//   <script nonce="…">s.addEventListener('ok-store-change', e => out.textContent = e.detail.value)</script>
export class OkStore extends LitElement {
  static styles = css`
    :host { display: contents; }
  `;

  /** Nombre de la base de datos IndexedDB que posee este elemento (default: 'outfitkit'). */
  @property() name?: string;

  /** La instancia de store que posee este elemento. Disponible tras la creación. */
  store!: Store;

  private unsubscribe?: () => void;
  private currentName?: string;

  connectedCallback(): void {
    super.connectedCallback();
    this.ensureStore();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unsubscribe?.();
    this.unsubscribe = undefined;
  }

  updated(changed: Map<string, unknown>): void {
    // Si cambia `name` en runtime, recreamos el store contra la nueva DB.
    if (changed.has('name')) this.ensureStore();
  }

  // Crea (o recrea si cambió `name`) el store y se (re)suscribe a sus cambios.
  private ensureStore(): void {
    if (this.store && this.currentName === this.name) return;
    this.unsubscribe?.();
    this.currentName = this.name;
    this.store = createStore({ name: this.name });
    this.unsubscribe = this.store.subscribe((value, key) => {
      this.dispatchEvent(
        new CustomEvent('ok-store-change', {
          detail: { key, value },
          bubbles: true,
          composed: true,
        }),
      );
    });
    void this.store.ready.then(() => {
      this.dispatchEvent(
        new CustomEvent('ok-store-ready', { bubbles: true, composed: true }),
      );
    });
  }

  /** Lee un valor del store (SÍNCRONO). */
  get<T = unknown>(key: string): T | undefined {
    return this.store.get<T>(key);
  }

  /** Escribe un valor en el store. */
  set<T = unknown>(key: string, value: T): void {
    this.store.set<T>(key, value);
  }

  /**
   * Actualiza un valor a partir del previo. Se llama `updateValue` (no `update`) porque `update`
   * es un método reservado del ciclo de vida de LitElement; usa el `.store.update()` directamente
   * si prefieres el nombre corto.
   */
  updateValue<T = unknown>(key: string, fn: (prev: T | undefined) => T): void {
    this.store.update<T>(key, fn);
  }

  /** Borra una clave. */
  delete(key: string): void {
    this.store.delete(key);
  }

  render(): unknown {
    return html`<slot></slot>`;
  }
}

define('ok-store', OkStore);

declare global {
  interface HTMLElementTagNameMap {
    'ok-store': OkStore;
  }
}
