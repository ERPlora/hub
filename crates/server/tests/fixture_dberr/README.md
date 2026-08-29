# `dberr` — módulo de fixture de hub#1074

Existe para **provocar un fallo de BD de verdad** por `/api/command` y `/api/query`, que es la única
forma honesta de comprobar que el texto del driver no sale al cliente: simular el error con un
`RuntimeError::Db` construido a mano no prueba que el camino real lo redacte.

- `dberr.notes.create` → INSERT con **clave ajena** a `dberr_topic`. Con un `topic_id` que no existe,
  Postgres devuelve la violación de FK entera (`sqlx: … violates foreign key constraint
  "dberr_note_topic_id_fkey" at line …`) — el mismo texto del issue.
- `dberr.notes.broken` → SELECT de una **columna inexistente**: la mitad de lectura del mismo camino.
- `dberr.notes.reject` → `expect_rows` con código de dominio, el canal que **NO** se redacta
  (ADR-0205/hub#139): sin este contraste, redactarlo todo pasaría el test igual.
