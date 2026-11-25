---
title: Facturar y vigilar los envíos a la AEAT
vertical: any
roles: responsable, administrador, empleado, gestoría, cliente (sin sesión)
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
10. INVOICE-F16, INVOICE-F17, INVOICE-F18 — una empleada solo ve, abre e imprime sus facturas: la de su compañero no le sale en la lista ni se abre por su número.
11. INVOICE-F19 — pagada por transferencia.
12. INVOICE-F08 — rectificada a mano.
13. INVOICE-F24 — la gestoría descarga el mes en Excel: la factura, su rectificativa y los tiques.
14. VERIFACTU-F16, VERIFACTU-F17 — los registros de la factura y de la rectificativa.
15. VERIFACTU-F20 — sin conexión a internet, un cobro entra en la cola y sale al volver.
16. VERIFACTU-F21, VERIFACTU-F22 — la cola, a mano y entrada a entrada.
17. VERIFACTU-F35 — se pregunta a la AEAT si ya tiene uno de la cola.
18. VERIFACTU-F24 — un registro rechazado por la AEAT.
19. VERIFACTU-F25 — ese registro, reenviado.
20. VERIFACTU-F30 — un registro enviado por error, anulado.
21. VERIFACTU-F26 — la cadena de huellas, verificada.
22. VERIFACTU-F27 — lo que tiene la AEAT.
23. VERIFACTU-F31 — los envíos, vigilados desde las pantallas.
