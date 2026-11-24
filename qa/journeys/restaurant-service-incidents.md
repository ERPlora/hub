---
title: Resolver las incidencias del servicio
vertical: restaurant
roles: responsable, empleado
---

Para qué: lo que se tuerce en un servicio con la sala llena: mesas que cambian, cuentas que se parten o se juntan, platos anulados, descuentos y productos agotados.

## Punto de partida

- Un servicio en marcha, como lo deja la mitad de `restaurant-lunch-service.md`: la caja abierta y varias mesas
  ocupadas con comandas enviadas a cocina.

## Recorrido

1. TABLE-F14 — en la mesa 4 eran cuatro, no tres.
2. TABLE-F15 — la mesa 4 se pasa a la 9, al sol.
3. TABLE-F16 — las mesas 9 y 10 son el mismo grupo: una sola cuenta.
4. TABLE-F17 — la mesa 9 pide dos cuentas.
5. SALE-F22 — uno de ellos paga solo lo suyo.
6. TABLE-F32 — la cuenta que queda, a nombre de un cliente con ficha.
7. TABLE-F13, SALE-F17 — un grupo se pasa a la barra: su cuenta se aparca.
8. TABLE-F24 — vuelven a una mesa: la cuenta aparcada se sienta en la 3.
9. TABLE-F12 — una cuenta abierta en la barra se lleva a la mesa 2.
10. SALE-F14, BASE-F84 — un 10 % de descuento a la mesa 2, con el PIN del responsable.
11. SALE-F15 — se invita el café.
12. SALE-F20, KITCHEN-F29 — un plato enviado por error se anula y la cocina recibe el aviso.
13. KITCHEN-F12 — en la cocina, un plato marcado listo por error vuelve atrás.
14. KITCHEN-F14 — la cocina marca urgente la ronda de la mesa 9.
15. KITCHEN-F20 — el camarero marca urgente otra ronda desde el TPV.
16. KITCHEN-F21 — una comanda se mueve desde la lista de Comandas.
17. KITCHEN-F23 — un pedido de barra, hecho a mano.
18. KITCHEN-F09, PRINTING-F11 — se reimprime una comanda que se ha manchado.
19. KITCHEN-F22 — se cancela la comanda de una mesa que se marcha sin comer.
20. KITCHEN-F24 — el pedido de barra hecho a mano ya no hace falta: se borra, pidiéndoselo al asistente.
21. INVENTORY-F29 — se acaba la tarta de queso: se le pide al asistente con otras palabras que las de la carta.
22. SALE-F07 — el TPV lo avisa al pedirla.
23. COMBO-F12 — se agota una elección del menú del día.
24. SALE-F09, BASE-F84 — una venta a precio libre en la sección «Varios».
25. SALE-F10 — medio kilo de gambas, al peso.
26. SALE-F18, BASE-F84 — se elimina una cuenta abierta por error.
27. TABLE-F20 — la cuenta de una mesa se elimina desde Ventas.
28. TABLE-F21 — se cierra a mano una mesa que se fue sin nada pendiente.
29. BASE-F60 — otro camarero coge la tableta sin perder la venta a medias.
30. CASH_REGISTER-F05 — una salida de 20,00 € para comprar hielo.
31. SALE-F06 — un cobro con tarjeta que se queda sin respuesta.
