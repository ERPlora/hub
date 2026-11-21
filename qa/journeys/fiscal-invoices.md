---
title: Facturar y vigilar los envíos a la AEAT
vertical: any
roles: responsable, administrador, empleado, cliente (sin sesión)
---

Para qué: las facturas que pide un cliente o se hacen a mano, sus rectificaciones y el seguimiento de cada registro fiscal hasta que la AEAT lo acepta.

## Punto de partida

- VeriFactu enviando en pruebas (`verifactu-setup.md`) y tiques cobrados de días anteriores.

## Recorrido

1. INVOICE-F12 — una serie para las facturas hechas a mano.
2. INVOICE-F13 — la serie, cambiada.
3. SALE-F04 — un cliente pide factura al cobrar: sus datos y su NIF.
4. SALE-F05 — en un negocio que exige cliente, un cobro sin él.
5. INVOICE-F05 — un tique de ayer pasa a factura completa en el mostrador.
6. INVOICE-F04 — otro cliente la pide él mismo desde su tique.
7. INVOICE-F03 — una factura a mano por un evento privado.
8. INVOICE-F16, INVOICE-F17 — esa factura, buscada y abierta.
9. INVOICE-F18 — en PDF.
10. INVOICE-F19 — pagada por transferencia.
11. INVOICE-F08 — rectificada a mano.
12. VERIFACTU-F16, VERIFACTU-F17 — los registros de la factura y de la rectificativa.
13. VERIFACTU-F20 — sin conexión a internet, un cobro entra en la cola y sale al volver.
14. VERIFACTU-F21, VERIFACTU-F22 — la cola, a mano y entrada a entrada.
15. VERIFACTU-F35 — se pregunta a la AEAT si ya tiene uno de la cola.
16. VERIFACTU-F24 — un registro rechazado por la AEAT.
17. VERIFACTU-F25 — ese registro, reenviado.
18. VERIFACTU-F30 — un registro enviado por error, anulado.
19. VERIFACTU-F26 — la cadena de huellas, verificada.
20. VERIFACTU-F27 — lo que tiene la AEAT.
21. VERIFACTU-F31 — los envíos, vigilados desde las pantallas.
