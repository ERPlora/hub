---
title: Un día de citas en la peluquería
vertical: hair_salon
roles: responsable, empleado
---

Para qué: abrir la caja, llevar la agenda del día (citas que llegan, se mueven, se cancelan o no se presentan), cobrar en el TPV y cerrar.

## Punto de partida

- El salón preparado (`salon-setup.md`) con sus profesionales y sus horarios (`salon-team-and-schedules.md`).
- La caja configurada y algunas citas ya reservadas para esta semana.

## Recorrido

1. BASE-F55 — Ana entra con su PIN en la tableta del mostrador.
2. CASH_REGISTER-F03 — abre la caja.
3. APPOINTMENT-F27 — la agenda de la semana.
4. APPOINTMENT-F02, APPOINTMENT-F01 — una llamada: corte el jueves a las 10:00 con Ana.
5. CUSTOMER-F25 — la clienta es nueva: su ficha, sin salir de la agenda.
6. APPOINTMENT-F28 — el aviso de la cita nueva.
7. APPOINTMENT-F03 — una cita pendiente, confirmada.
8. APPOINTMENT-F04 — la cita del jueves pasa a las 11:00 con otro profesional.
9. APPOINTMENT-F22 — una nota en la cita: «trae foto del color»; después, el asistente le dice a Ana el teléfono de la clienta que tiene puesto la cita.
10. APPOINTMENT-F16 — la hora de comer de Ana, bloqueada.
11. APPOINTMENT-F07 — llega la clienta de las 10:00: empieza el servicio.
12. APPOINTMENT-F08 — la cita, completada.
13. APPOINTMENT-F17, SALE-F26 — se cobra en el TPV desde la agenda.
14. SALE-F38, SERVICE-F09 — antes de cobrar se añade un tratamiento que no estaba en la cita.
15. SALE-F02 — paga con tarjeta.
16. APPOINTMENT-F09 — la clienta de las 12:00 no se presenta.
17. APPOINTMENT-F05 — otra cancela por teléfono.
18. APPOINTMENT-F10 — el historial de una cita.
19. APPOINTMENT-F20 — las citas de una clienta, en su ficha.
20. APPOINTMENT-F12 — un tinte cada cuatro semanas, como cita periódica.
21. APPOINTMENT-F13 — se reservan las citas de la serie.
22. APPOINTMENT-F14 — desde la tercera, a otra hora.
23. APPOINTMENT-F15 — la serie, en pausa y reactivada.
24. APPOINTMENT-F11 — el propietario borra una cita de prueba.
25. BASE-F55, APPOINTMENT-F27 — Bea, empleada, entra con su PIN: en la agenda solo están su fila y sus citas.
26. CASH_REGISTER-F09 — Ana cierra la caja.
