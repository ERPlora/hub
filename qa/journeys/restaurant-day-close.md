---
title: Cerrar el día del restaurante
vertical: restaurant
roles: responsable, empleado
---

Para qué: comprobar que no queda nada abierto, cuadrar la caja con su descuadre e imprimir el cierre.

## Punto de partida

- El servicio terminado (`restaurant-lunch-service.md`), sin mesas abiertas por cobrar y la caja abierta con los
  cobros del día.

## Recorrido

1. TABLE-F22 — las cuentas de la sala de hoy.
2. TABLE-F23 — el administrador borra del historial una cuenta cerrada de prueba.
3. KITCHEN-F25 — el historial de cocina del día.
4. CASH_REGISTER-F08 — lo pendiente antes de cerrar.
5. CASH_REGISTER-F06 — el cajón, por billetes y monedas.
6. CASH_REGISTER-F07 — el empleado cuenta a ciegas.
7. CASH_REGISTER-F09 — se cierra con 5,00 € de menos.
8. CASH_REGISTER-F11 — el responsable revisa el descuadre.
9. SALE-F08 — con la caja cerrada, un café de última hora no se cobra en efectivo.
10. SALE-F02, CASH_REGISTER-F17 — se cobra con tarjeta y sale como cobro fuera de turno.
11. CASH_REGISTER-F16, PRINTING-F17 — el informe Z, en papel.
12. CASH_REGISTER-F12 — la caja, en Inicio.
13. SALE-F28, SALE-F29 — el empleado solo ve en Ventas los cobros que hizo él y reimprime uno.
14. SALE-F28 — el responsable ve las ventas de todos y las cifras del día, también en Inicio, con las del empleado.
15. INVENTORY-F17 — lo que se ha quedado bajo de stock.
16. VERIFACTU-F31 — que todo ha llegado a la AEAT.
17. BASE-F09 — la actividad del día.
18. ATTENDANCE-F01 — el responsable ficha la salida.
19. BASE-F61 — cierra la sesión.
