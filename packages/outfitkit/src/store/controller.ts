// StoreController — puente entre el `store` reactivo y un componente Lit. Implementa la interfaz
// `ReactiveController` de Lit: se suscribe al store en `hostConnected` y llama a `host.requestUpdate()`
// en cada cambio, desuscribiéndose en `hostDisconnected`. Así un componente se re-renderiza solo
// cuando cambia el estado que le interesa.
//
// Uso típico dentro de un LitElement:
//   private state = new StoreController(this, store, 'theme');
//   render() { return html`<span>${this.state.value}</span>`; }
//   // ...this.state.set('dark');  this.state.update(v => !v);
//
// Si no pasas `key`, se suscribe a TODOS los cambios del store (útil para vistas que dependen de
// varias claves).

import type { ReactiveController, ReactiveControllerHost } from 'lit';
import type { Store } from './store.js';

export class StoreController<T = unknown> implements ReactiveController {
  private host: ReactiveControllerHost;
  private store: Store;
  private key?: string;
  private unsubscribe?: () => void;

  constructor(host: ReactiveControllerHost, store: Store, key?: string) {
    this.host = host;
    this.store = store;
    this.key = key;
    host.addController(this);
  }

  /** Valor actual de la clave observada (o `undefined` si el controller observa todo el store). */
  get value(): T | undefined {
    return this.key === undefined ? undefined : this.store.get<T>(this.key);
  }

  /** Escribe en la clave observada. No-op si el controller no tiene clave. */
  set(value: T): void {
    if (this.key !== undefined) this.store.set<T>(this.key, value);
  }

  /** Actualiza la clave observada a partir del valor previo. No-op si no hay clave. */
  update(fn: (prev: T | undefined) => T): void {
    if (this.key !== undefined) this.store.update<T>(this.key, fn);
  }

  hostConnected(): void {
    const onChange = () => this.host.requestUpdate();
    this.unsubscribe =
      this.key === undefined
        ? this.store.subscribe(onChange)
        : this.store.subscribe(this.key, onChange);
  }

  hostDisconnected(): void {
    this.unsubscribe?.();
    this.unsubscribe = undefined;
  }
}
