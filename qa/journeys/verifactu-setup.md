---
title: Encender VeriFactu y dejarlo enviando en pruebas
vertical: any
roles: propietario, administrador
---

Para qué: activar VeriFactu, decidir quién remite los registros a la AEAT y comprobarlo todo contra el entorno de pruebas antes de facturar de verdad.

## Punto de partida

- Un negocio con Facturación y su emisor configurado (`restaurant-new-business.md`).
- Un certificado de pruebas para el entorno de pruebas de la AEAT. La transmisión real y los certificados reales
  solo se tocan con la supervisión de quien los custodia.

## Recorrido

1. VERIFACTU-F01 — VeriFactu, encendido desde Apps.
2. VERIFACTU-F32 — una vez encendido, ya no se puede apagar.
3. VERIFACTU-F12 — la declaración responsable.
4. VERIFACTU-F04 — quién remite: el certificado del negocio o ERPlora.
5. VERIFACTU-F05 — el otorgamiento de representación, para que remita ERPlora.
6. VERIFACTU-F06 — el otorgamiento, enviado otra vez.
7. VERIFACTU-F02 — o, en su lugar, el certificado propio del negocio.
8. VERIFACTU-F34 — el certificado, renovado.
9. VERIFACTU-F03 — el certificado propio, quitado.
10. VERIFACTU-F10 — la conexión con la AEAT, en pruebas.
11. VERIFACTU-F11 — una factura de prueba.
12. VERIFACTU-F29 — un negocio que viene de otro programa sigue su cadena.
13. VERIFACTU-F08 — el paso a producción, solo en un negocio real y con su certificado.
14. VERIFACTU-F09 — de vuelta a pruebas.
