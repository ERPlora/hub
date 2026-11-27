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
5. TIP-F03 — la mesa 8 añadió 3,00 € de propina en el datáfono.
6. TIP-F06 — el responsable la deja en 2,50 € y anula otra apuntada por error.
7. TIP-F05 — el bote de la barra, 12,00 €.
8. CASH_REGISTER-F06 — el cajón, por billetes y monedas.
9. CASH_REGISTER-F07 — el empleado cuenta a ciegas.
10. CASH_REGISTER-F18 — las propinas del día, aparte, en la sesión y en la ventana del cierre.
11. TIP-F13 — el responsable ve las propinas del día por persona y por turno, y las exporta en CSV.
12. CASH_REGISTER-F09 — se cierra con 5,00 € de menos.
13. CASH_REGISTER-F11 — el responsable revisa el descuadre.
14. CASH_REGISTER-F11 — el empleado solo tiene en Caja los turnos que abrió o cerró él y el abierto; el de un compañero no se abre ni por su número.
15. SALE-F08 — con la caja cerrada, un café de última hora no se cobra en efectivo.
16. SALE-F02, CASH_REGISTER-F17 — se cobra con tarjeta y sale como cobro fuera de turno.
17. CASH_REGISTER-F16, PRINTING-F17 — el informe Z, en papel.
18. CASH_REGISTER-F12 — la caja, en Inicio.
19. TIP-F14 — el empleado ve sus propinas de hoy y de la semana, sin nada de gestión.
20. SALE-F28, SALE-F29 — el empleado solo ve en Ventas los cobros que hizo él, con las cifras de esos cobros, y reimprime uno.
21. SALE-F28 — el responsable ve las ventas de todos y las cifras del día, también en Inicio, con las del empleado.
22. INVENTORY-F17 — lo que se ha quedado bajo de stock.
23. VERIFACTU-F31 — que todo ha llegado a la AEAT.
24. BASE-F09 — la actividad del día.
25. ATTENDANCE-F01 — el responsable ficha la salida.
26. BASE-F61 — cierra la sesión.
