---
title: Anular y devolver una venta cobrada
vertical: restaurant
roles: propietario, responsable, empleado
---

Para qué: deshacer un cobro equivocado y devolver parte de una cuenta, con su reflejo en la caja, las facturas y VeriFactu.

## Punto de partida

- Ventas cobradas del día y la caja abierta, como las deja `restaurant-lunch-service.md`.
- VeriFactu encendido en pruebas (`verifactu-setup.md`).
- Lucía, empleada con un rol propio que dice «No» a anular y «Con aprobación» a devolver, con una venta suya cobrada.

## Recorrido

1. SALE-F28 — la venta de la mesa 4, en el historial.
2. SALE-F29, PRINTING-F08 — se reimprime su tique.
3. SALE-F30, BASE-F84 — un empleado anula una venta cobrada a la mesa equivocada, con el PIN del responsable.
4. TABLE-F19 — la mesa deja de contar ese cobro, sin reabrir su cuenta.
5. CASH_REGISTER-F14 — la caja compensa la anulación.
6. SALE-F30, BASE-F84 — Lucía intenta anular su venta: su rol se lo niega antes de empezar y nadie tiene que poner un PIN.
7. BASE-F100 — Lucía le pide la misma anulación al asistente, que tampoco la hace ni pide un PIN.
8. SALE-F31, BASE-F84 — Lucía devuelve esa venta, con el PIN del responsable.
9. SALE-F31 — a la mesa 8 no le gustó la tarta: se devuelve en efectivo.
10. CASH_REGISTER-F15 — la devolución, en la caja.
11. INVOICE-F16, INVOICE-F17 — el tique y su rectificativa, en Facturas.
12. VERIFACTU-F16 — los registros de la venta, la anulación y la devolución.
13. BASE-F85 — el propietario lee lo que aprobó el PIN del responsable y, por su rol, la tarta que devolvió él mismo; lo
    filtra y lo exporta.
