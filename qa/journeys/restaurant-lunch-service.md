---
title: Abrir y servir las comidas
vertical: restaurant
roles: responsable, empleado
---

Para qué: un servicio de mediodía normal, desde que se abre la caja hasta que las mesas pagan en efectivo, con tarjeta o a medias.

## Punto de partida

- La carta, la sala, la cocina y la impresión preparadas: `restaurant-menu-setup.md`,
  `restaurant-floor-and-kitchen-setup.md` y `printing-setup.md`.
- Una reserva confirmada para hoy a las 14:00, a nombre de Lucía, en la mesa 8 (`restaurant-reservations.md`).
- La tableta de la barra, la de la cocina y el móvil de un camarero.

## Recorrido

1. BASE-F55 — el responsable entra con su PIN en la tableta de la barra.
2. ATTENDANCE-F01 — ficha la entrada.
3. CASH_REGISTER-F04 — antes de abrir la caja, el primer café no se puede cobrar en efectivo.
4. CASH_REGISTER-F03 — fondo de 150,00 €; el café ya se cobra.
5. TABLE-F09 — la sala vacía, al abrir.
6. TABLE-F10, SALE-F19 — un grupo sin reserva: mesa 4, tres comensales.
7. TABLE-F10, SALE-F19 — dos clientes más: mesa 6, solo bebidas.
8. SALE-F11, MODIFIER-F06 — en la mesa 4, un entrecot al punto.
9. SALE-F12, COMBO-F07 — dos menús del día.
10. CUSTOMER-F17 — la mesa 4 es de una clienta que ya tiene ficha.
11. SALE-F40, MODIFIER-F12 — los alérgenos de la tarta con «Extra de queso».
12. SALE-F41 — la clienta es alérgica al gluten: se marca en su plato.
13. SALE-F13 — «sin cebolla» en el segundo menú.
14. SALE-F20, KITCHEN-F18, PRINTING-F10 — la ronda de la mesa 4 sale en la pantalla de cocina y en papel.
15. KITCHEN-F16, KITCHEN-F10 — en la cocina suena y entra la comanda.
16. KITCHEN-F06, KITCHEN-F07, KITCHEN-F32 — el menú, la nota y la alergia, en la tarjeta.
17. KITCHEN-F15 — lo que queda por cocinar.
18. KITCHEN-F11 — los primeros, listos.
19. KITCHEN-F19 — el camarero lo ve desde el TPV.
20. KITCHEN-F13 — se entregan.
21. TABLE-F28 — llega Lucía: su reserva se sienta en la mesa 8.
22. SALE-F16 — la cuenta de la mesa 8, a nombre del camarero que la atiende.
23. TABLE-F33 — cuánto lleva cada mesa.
24. TABLE-F11 — se vuelve a la mesa 4 a por los postres.
25. TABLE-F34 — la mesa 4 pide la cuenta.
26. SALE-F21, PRINTING-F09 — la precuenta de la mesa 4.
27. COMBO-F08, COMBO-F09 — los menús y el suplemento del entrecot, en la cuenta de la mesa 4.
28. SALE-F01, PRINTING-F07, PRINTING-F13 — la mesa 4 paga en efectivo con un billete de 50 €.
29. TABLE-F18, CASH_REGISTER-F13 — la mesa 4 queda libre y el cobro, en la caja.
30. BASE-F08 — en el móvil del propietario, los paneles de Inicio se ponen al día con ese cobro.
31. SALE-F02 — la mesa 8 paga con tarjeta.
32. SALE-F03 — la mesa 6 paga a medias, en efectivo y con tarjeta.
