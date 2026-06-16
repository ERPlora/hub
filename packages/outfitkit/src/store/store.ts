// Store de estado reactivo respaldado por IndexedDB. Parte del CORE de OutfitKit, reutilizable por
// cualquier componente (vía `StoreController`) o por código suelto (Django/JS) vía el singleton
// `store` o `createStore()`.
//
// Modelo: la FUENTE DE VERDAD síncrona es una caché en memoria (Map). IndexedDB solo PERSISTE en
// segundo plano (fire-and-forget). Así `get()` es síncrono y `set()` notifica a los suscriptores al
// instante; la escritura a disco ocurre detrás (puedes esperarla con `flush()`).
//
// CERO dependencias externas. CSP-safe (sin eval/new Function).

import { createIdb, type IdbAdapter } from './idb.js';

/** Callback de suscripción: recibe el nuevo valor y la clave que cambió. En `clear()`, value=undefined. */
export type StoreSubscriber<T = unknown> = (value: T | undefined, key: string) => void;

export interface StoreOptions {
  /** Nombre de la base de datos IndexedDB (default: 'outfitkit'). */
  name?: string;
  /** Nombre del objectStore dentro de la DB (default: 'kv'). */
  storeName?: string;
}

export interface Store {
  /** Resuelve cuando la caché se ha hidratado desde IndexedDB. Espérala antes de leer al arrancar. */
  readonly ready: Promise<void>;
  /** Lee un valor de la caché (SÍNCRONO). `undefined` si no existe. */
  get<T = unknown>(key: string): T | undefined;
  /** Escribe un valor: actualiza caché, notifica suscriptores y persiste en IndexedDB (fire-and-forget). */
  set<T = unknown>(key: string, value: T): void;
  /** Actualiza un valor a partir del anterior: `fn(prev) => next`. */
  update<T = unknown>(key: string, fn: (prev: T | undefined) => T): void;
  /** Borra una clave. */
  delete(key: string): void;
  /** Alias de `delete`. */
  remove(key: string): void;
  /** Vacía el store entero. */
  clear(): void;
  /** ¿Existe la clave en la caché? */
  has(key: string): boolean;
  /** Claves actuales. */
  keys(): string[];
  /** Pares [clave, valor] actuales. */
  entries(): Array<[string, unknown]>;
  /** Suscríbete a una clave concreta. Devuelve la función de desuscripción. */
  subscribe<T = unknown>(key: string, cb: StoreSubscriber<T>): () => void;
  /** Suscríbete a TODOS los cambios. Devuelve la función de desuscripción. */
  subscribe(cb: StoreSubscriber): () => void;
  /** Resuelve cuando se han escrito a IndexedDB todas las operaciones pendientes. */
  flush(): Promise<void>;
}

export function createStore(options: StoreOptions = {}): Store {
  const idb: IdbAdapter = createIdb(options.name, options.storeName);

  // Caché síncrona en memoria.
  const cache = new Map<string, unknown>();

  // Suscriptores por clave + suscriptores globales (key === '*' interno).
  const keySubs = new Map<string, Set<StoreSubscriber>>();
  const allSubs = new Set<StoreSubscriber>();

  // Cola de escrituras pendientes a IndexedDB, encadenada para que `flush()` espere a todas.
  let pending: Promise<void> = Promise.resolve();
  function enqueue(op: () => Promise<void>): void {
    // Encadenamos (y tragamos errores: el adaptador ya degrada, pero por si acaso).
    pending = pending.then(op).catch(() => {});
  }

  // Hidratación inicial: vuelca IndexedDB a la caché. NO notifica (aún no hay suscriptores).
  const ready: Promise<void> = idb.getAll().then((rows) => {
    for (const [key, value] of rows) {
      if (!cache.has(key)) cache.set(key, value);
    }
  });

  function notify(key: string, value: unknown): void {
    const subs = keySubs.get(key);
    if (subs) for (const cb of [...subs]) cb(value, key);
    for (const cb of [...allSubs]) cb(value, key);
  }

  const store: Store = {
    ready,

    get<T = unknown>(key: string): T | undefined {
      return cache.get(key) as T | undefined;
    },

    set<T = unknown>(key: string, value: T): void {
      cache.set(key, value);
      notify(key, value);
      enqueue(() => idb.set(key, value));
    },

    update<T = unknown>(key: string, fn: (prev: T | undefined) => T): void {
      const next = fn(cache.get(key) as T | undefined);
      store.set(key, next);
    },

    delete(key: string): void {
      const existed = cache.delete(key);
      if (existed) {
        notify(key, undefined);
        enqueue(() => idb.delete(key));
      }
    },

    remove(key: string): void {
      store.delete(key);
    },

    clear(): void {
      const keys = [...cache.keys()];
      cache.clear();
      for (const key of keys) notify(key, undefined);
      enqueue(() => idb.clear());
    },

    has(key: string): boolean {
      return cache.has(key);
    },

    keys(): string[] {
      return [...cache.keys()];
    },

    entries(): Array<[string, unknown]> {
      return [...cache.entries()];
    },

    subscribe(
      keyOrCb: string | StoreSubscriber,
      maybeCb?: StoreSubscriber,
    ): () => void {
      // Sobrecarga: subscribe(cb) → todos los cambios; subscribe(key, cb) → una clave.
      if (typeof keyOrCb === 'function') {
        const cb = keyOrCb;
        allSubs.add(cb);
        return () => allSubs.delete(cb);
      }
      const key = keyOrCb;
      const cb = maybeCb as StoreSubscriber;
      let subs = keySubs.get(key);
      if (!subs) {
        subs = new Set();
        keySubs.set(key, subs);
      }
      subs.add(cb);
      return () => {
        subs.delete(cb);
        if (subs.size === 0) keySubs.delete(key);
      };
    },

    flush(): Promise<void> {
      return pending;
    },
  };

  return store;
}

/** Singleton por defecto (DB 'outfitkit', store 'kv'). Cómodo para uso global rápido. */
export const store: Store = createStore();
