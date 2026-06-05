-- Traceability · esquema inicial (SQLite). Portado fielmente de modules/m_traceability/models.py.
-- Modelos: TraceEvent (un evento de trazabilidad por producto/lote/serie) y TraceChain
-- (enlace entre eventos que comparten chain_id; permite reconstruir la cadena y el impacto
-- de retirada). Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Evento de trazabilidad: un hito en el ciclo de vida de una entidad
-- (received|produced|transferred|sold|returned|scrapped|recalled).
-- entity_type ∈ (lot|serial|product); entity_ref es el identificador libre del lote/serie/producto.
-- occurred_at puede diferir de created_at (eventos retroactivos / back-dated).
-- recorded_by: usuario que registró el evento (NULL = registrado por el sistema).
-- metadata: bolsa JSON libre (atributos de lote, lecturas de sensores, etc.).
CREATE TABLE IF NOT EXISTS traceability_event (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    event_type            TEXT NOT NULL,                 -- received|produced|transferred|sold|returned|scrapped|recalled
    entity_type           TEXT NOT NULL,                 -- lot|serial|product
    entity_ref            TEXT NOT NULL,
    quantity              NUMERIC NOT NULL DEFAULT 0,     -- unidades, peso, etc.
    source_ref            TEXT NOT NULL DEFAULT '',       -- almacén/proveedor origen (libre)
    destination_ref       TEXT NOT NULL DEFAULT '',       -- destino (cliente/almacén) (libre)
    related_document_type TEXT NOT NULL DEFAULT '',       -- sale|invoice|purchase_order... (libre)
    related_document_ref  TEXT NOT NULL DEFAULT '',
    occurred_at           TEXT NOT NULL,                  -- ISO datetime: cuándo ocurrió el hito
    recorded_by           TEXT,                           -- usuario que lo registró (NULL = sistema)
    notes                 TEXT NOT NULL DEFAULT '',
    metadata              TEXT NOT NULL DEFAULT '{}',     -- JSON libre
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE INDEX IF NOT EXISTS ix_trace_event_hub_entity      ON traceability_event (hub_id, entity_type, entity_ref);
CREATE INDEX IF NOT EXISTS ix_trace_event_hub_type        ON traceability_event (hub_id, event_type);
CREATE INDEX IF NOT EXISTS ix_trace_event_hub_occurred_at ON traceability_event (hub_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_traceability_event_hub     ON traceability_event (hub_id, is_deleted);

-- Cadena de trazabilidad: agrupa los eventos de una misma entidad física por chain_id
-- (formato "entity_type:entity_ref"). parent_event_id se fija cuando la entrada se creó como
-- evento aguas abajo de otro (p.ej. una entrada 'transferred' cuyo padre es el 'received' del
-- mismo lote). Sirve para reconstruir el grafo y calcular el impacto de una retirada (recall).
CREATE TABLE IF NOT EXISTS traceability_chain (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    chain_id        TEXT NOT NULL,                        -- "<entity_type>:<entity_ref>"
    parent_event_id TEXT,                                 -- evento padre (NULL = raíz de la cadena)
    event_id        TEXT NOT NULL,                        -- evento al que pertenece esta entrada
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (event_id)        REFERENCES traceability_event (id) ON DELETE CASCADE,
    FOREIGN KEY (parent_event_id) REFERENCES traceability_event (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_trace_chain_hub_chain_id ON traceability_chain (hub_id, chain_id);
CREATE INDEX IF NOT EXISTS ix_trace_chain_hub_parent   ON traceability_chain (hub_id, parent_event_id);
CREATE INDEX IF NOT EXISTS idx_traceability_chain_hub  ON traceability_chain (hub_id, is_deleted);
