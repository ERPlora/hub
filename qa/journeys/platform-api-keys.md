---
title: Conectar otro programa por la API
vertical: any
roles: propietario, administrador
---

Para qué: dar a otro programa una llave de API con los permisos justos, consultar la documentación y retirarla cuando ya no se usa.

## Punto de partida

- Un negocio con Inventario y otras apps activadas, y otro programa que quiere leer sus productos.

## Recorrido

1. BASE-F91 — la documentación de la API, visible.
2. BASE-F90 — la documentación de la API.
3. BASE-F86 — el administrador crea una llave que solo lee Inventario; el otro programa la usa para leer y para escribir.
4. BASE-F89 — la llave del administrador, con lo que puede y quién la creó.
5. BASE-F87 — la llave, rotada.
6. BASE-F125 — con el token rotado; en erplora.com, el propietario baja de rol al administrador que creó la llave y después lo saca del negocio.
7. BASE-F88 — la llave, revocada.
