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
7. INVOICE-F03 — en la serie del primer paso, una factura a mano a una empresa por un evento privado, de ayer, con vencimiento a 30 días y retención del 15 %, y otra de ayer que vencía ayer mismo.
8. INVOICE-F16, INVOICE-F17 — las dos, buscadas y abiertas; entre las vencidas sale solo la segunda.
9. INVOICE-F18 — la primera, impresa: lo retenido y lo que se cobra, además de su total.
10. INVOICE-F25 — la primera, descargada en PDF: dice lo mismo que el papel y su QR, leído con el móvil, abre el registro de esa factura.
11. INVOICE-F26 — la primera, enviada por correo a la dirección de la empresa: la ficha dice a quién y cuándo, llega con el mismo PDF y la respuesta vuelve al propietario; y otra vez, a otra dirección.
12. INVOICE-F16, INVOICE-F17, INVOICE-F18 — una empleada solo ve, abre e imprime sus facturas: la de su compañero no le sale en la lista ni se abre por su número.
13. INVOICE-F19 — la vencida, pagada por transferencia: ya no sale entre las vencidas.
14. INVOICE-F08 — rectificada a mano.
15. INVOICE-F24 — la gestoría descarga el mes en Excel: la factura con su retención, la rectificativa y los tiques.
16. VERIFACTU-F16, VERIFACTU-F17 — los registros de la factura y de la rectificativa.
17. VERIFACTU-F20 — sin conexión a internet, un cobro entra en la cola y sale al volver.
18. VERIFACTU-F21, VERIFACTU-F22 — la cola, a mano y entrada a entrada.
19. VERIFACTU-F35 — se pregunta a la AEAT si ya tiene uno de la cola.
20. VERIFACTU-F24 — un registro rechazado por la AEAT.
21. VERIFACTU-F25 — ese registro, reenviado.
22. VERIFACTU-F30 — un registro enviado por error, anulado.
23. VERIFACTU-F26 — la cadena de huellas, verificada.
24. VERIFACTU-F27 — lo que tiene la AEAT.
25. VERIFACTU-F31 — los envíos, vigilados desde las pantallas.
