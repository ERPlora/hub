// Adaptador mínimo de IndexedDB (solo promesas, CERO dependencias). Un único objectStore
// clave→valor (estilo localStorage pero asíncrono y con objetos estructurados). Pensado para
// respaldar el `store` reactivo: la fuente síncrona es una caché en memoria; esto solo persiste.
//
// Si el entorno NO tiene `indexedDB` (SSR, tests, navegadores antiguos), degrada a NO-OP: la
// persistencia se desactiva en silencio (el store sigue funcionando solo en memoria). Los errores
// se tragan y se reportan por consola; NUNCA se lanzan al consumidor para no romper la UI.

export interface IdbAdapter {
  /** Lee TODO el objectStore como pares [clave, valor] (para hidratar la caché al arrancar). */
  getAll(): Promise<Array<[string, unknown]>>;
  /** Escribe (o reemplaza) un valor por clave. */
  set(key: string, val: unknown): Promise<void>;
  /** Borra una clave. */
  delete(key: string): Promise<void>;
  /** Vacía el objectStore entero. */
  clear(): Promise<void>;
}

const DEFAULT_DB = 'outfitkit';
const DEFAULT_STORE = 'kv';

// Detección perezosa: `indexedDB` puede no existir (Node, workers sin soporte, etc.).
function hasIndexedDB(): boolean {
  return typeof indexedDB !== 'undefined' && indexedDB !== null;
}

// Adaptador NO-OP: todo resuelve sin hacer nada (persistencia desactivada).
function noopAdapter(): IdbAdapter {
  return {
    getAll: () => Promise.resolve([]),
    set: () => Promise.resolve(),
    delete: () => Promise.resolve(),
    clear: () => Promise.resolve(),
  };
}

// Envuelve una IDBRequest en una promesa.
function promisify<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/**
 * Crea un adaptador IndexedDB para una DB/objectStore concretos. Si no hay soporte de IndexedDB,
 * devuelve un adaptador NO-OP (memoria-solo). La apertura es perezosa y se cachea; si falla, se
 * cae también a NO-OP (sin lanzar). `dbName`/`storeName` por defecto: 'outfitkit' / 'kv'.
 */
export function createIdb(dbName = DEFAULT_DB, storeName = DEFAULT_STORE): IdbAdapter {
  if (!hasIndexedDB()) return noopAdapter();

  let dbPromise: Promise<IDBDatabase> | null = null;

  function openDb(): Promise<IDBDatabase> {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
      const req = indexedDB.open(dbName, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(storeName)) {
          db.createObjectStore(storeName);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return dbPromise;
  }

  // Ejecuta una operación dentro de una transacción; ante CUALQUIER error degrada a `fallback`
  // (sin lanzar) y lo reporta por consola.
  async function withStore<T>(
    mode: IDBTransactionMode,
    fn: (store: IDBObjectStore) => Promise<T>,
    fallback: T,
  ): Promise<T> {
    try {
      const db = await openDb();
      const tx = db.transaction(storeName, mode);
      const store = tx.objectStore(storeName);
      return await fn(store);
    } catch (err) {
      console.warn('[outfitkit/store] IndexedDB falló, se ignora la operación:', err);
      return fallback;
    }
  }

  return {
    getAll() {
      return withStore<Array<[string, unknown]>>(
        'readonly',
        async (store) => {
          const keys = await promisify(store.getAllKeys());
          const values = await promisify(store.getAll());
          const out: Array<[string, unknown]> = [];
          for (let i = 0; i < keys.length; i++) {
            out.push([String(keys[i]), values[i]]);
          }
          return out;
        },
        [],
      );
    },
    set(key, val) {
      return withStore<void>(
        'readwrite',
        async (store) => {
          await promisify(store.put(val, key));
        },
        undefined,
      );
    },
    delete(key) {
      return withStore<void>(
        'readwrite',
        async (store) => {
          await promisify(store.delete(key));
        },
        undefined,
      );
    },
    clear() {
      return withStore<void>(
        'readwrite',
        async (store) => {
          await promisify(store.clear());
        },
        undefined,
      );
    },
  };
}
