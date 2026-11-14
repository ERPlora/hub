# Workbook — Propinas (app)
Prefijo: TIP
Alcance MVP: etapa TPV (restaurante y peluquería)
Estado de la app: no hecha — especificación escrita el 2026-11-14 (hub#562); el código va por hub#1497 a hub#1502

> Manual de usuario y especificación de la app `tip`. Se escribe **antes** que el código: no se programa
> nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde (servidor y
> páginas). Es una app nueva, no un porte: el módulo de Ventas del producto actual no tenía propinas. Su
> ficha funcional es Toast, completada con lo que hacen Square, Lightspeed, SumUp, Odoo, Shopify y los TPV
> españoles (Revo, Ágora, Glop); ver «Referencia adoptada».

## Para qué sirve y para quién

Propinas guarda **la propina que el cliente deja al pagar**, con tarjeta o en efectivo, y **de quién es**.
La propina no es una venta: no lleva IVA, no cambia el tique y no llega a la AEAT. Se anota en el propio
cobro de Ventas, con un toque (un porcentaje sugerido, otra cantidad o «quédese el cambio»), entra en la
caja si es en efectivo y se le paga después a quien le toca. Sirve a los dos negocios:

- En el **restaurante**, la propina es del camarero que atiende la mesa o, si el negocio lo decide, va a un
  bote que se reparte entre sala, barra y cocina por horas fichadas o por puntos.
- En la **peluquería**, la propina es de la profesional que atendió a la clienta.

Quién la usa:

- El **empleado** que cobra: anota la propina al cobrar o después sobre el tique, y ve las suyas.
- El **responsable**: además ajusta o anula una propina, define el reparto, lo aprueba y paga las
  propinas, y ve el informe de todo el equipo.
- El **propietario** y el **administrador**: todo, y además los ajustes.

Propinas no cobra (es de Ventas), no cuadra la caja (es de Caja: Propinas le apunta lo que entra y sale) y
no hace nóminas.

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó (consultado el 2026-11-14).

- **La propina se anota en el cobro, con sugerencias y otra cantidad.** Square (en España) ofrece tres
  sugerencias, «otro importe» y «sin propina», en importes fijos para las cuentas pequeñas y en porcentaje
  para las grandes ([Square — liquidar pagos y gestionar propinas](https://squareup.com/help/es/es/article/8375-settle-payments-and-manage-tips));
  Shopify POS, hasta tres sugerencias y una cantidad libre ([Shopify — propinas en el TPV](https://help.shopify.com/manual/sell-in-person/transactions/tips));
  Odoo, el botón «Tip» de la pantalla de pago ([Odoo — propinas](https://www.odoo.com/documentation/17.0/applications/sales/point_of_sale/restaurant/tips.html));
  Lightspeed, «Add tip» en el pago ([Lightspeed K-Series — propinas](https://k-series-support.lightspeedhq.com/hc/articles/4415116773403)).
- **Sugerencias por forma de pago**: Revo XEF pide propina según la forma de pago y desde su versión 5.0 sugiere
  propinas por método ([Revo — formas de pago](https://support.revo.works/es/articles/66),
  [Revo XEF 5.0](https://support.revoxef.works/es/articles/1096)); Ágora deja configurar la propina sugerida
  al cobrar con tarjeta ([Ágora Payments](https://www.agorapos.com/agora-payments/)).
- **El cambio, de propina, si el empleado lo confirma**: Revo «convierte el cambio en propina» (también «con
  confirmación»), SumUp ofrece «Use for tip» cuando lo pagado pasa de la cuenta
  ([SumUp — gestión de propinas](https://help.sumup.com/en-GB/pos/articles/75000112645-tips-management)) y
  Lightspeed calcula la propina de lo entregado.
- **La propina es de quien atiende o cobra**: Square la atribuye a quien procesa el pago y por defecto
  «cada empleado se queda con las que recibe»
  ([Square — repartir propinas](https://squareup.com/help/es/es/article/8141-tip-out-team-members-with-square-for-restaurants));
  Toast, a quien lleva la cuenta ([Toast — cómo gestiona las propinas](https://support.toasttab.com/en/article/How-Toast-Handles-and-Distributes-Tips));
  SumUp y Lightspeed, a quien cobra. El bote y el reparto entre puestos son **opcionales** (Square y Toast los
  activan a mano; Toast con su Tips Manager).
- **La propina en efectivo que no pasa por el TPV se declara al cerrar el turno**, con aviso si es baja,
  como en Toast ([Toast — declarar propinas en efectivo](https://support.toasttab.com/en/article/Declaring-Cash-Tips)).
- **La caja cuenta la propina aparte**: SumUp la pone en el informe X y en el Z; Square da en el informe de turno
  las propinas con tarjeta y el efectivo que se debe al personal
  ([Square — informe de turno](https://squareup.com/help/es/es/article/8140-run-shift-report-with-square-for-restaurants)).
  Y pagar en efectivo propinas cobradas con tarjeta se apunta como salida de caja, o el cajón parece corto: es
  la queja repetida en los foros de Square
  ([comunidad de Square — propinas y caja](https://community.squareup.com/t5/Archived-Discussions-Read-Only/How-do-I-track-cash-in-my-till-and-pay-out-and-account-for-tips/td-p/2511/page/3))
  y de Toast ([comunidad de Toast — depósitos y propinas de fin de noche](https://community.toasttab.com/t5/back-office-team/server-bartender-tip-logs-and-end-of-night-deposits/m-p/3863)).
- **En España se deja poco**: el 63 % de quien deja propina deja menos del 5 % de la cuenta, el 35 % entre el 5 y
  el 10 % y solo el 2 % más (TheFork Lab, en
  [Finantres](https://finantresnoticias.com/negocios-y-autonomos/propina-se-enfria-en-restaurantes-dato-deben-mirar-pequenos-negocios/)).
  De ahí las sugerencias de fábrica: 3 %, 5 % y 10 %.
- **La propina voluntaria no lleva IVA** (ver «Por qué la propina no entra en el tique» en «Para quien lo
  mantiene»): [Garrigues — cómo tributan las propinas](https://www.garrigues.com/es_ES/noticia/como-tributan-las-propinas)
  y el blog de Ágora ([¿debemos declarar las propinas?](https://www.agorapos.com/blog/debemos-declarar-las-propinas/)).

## Antes de empezar

- **Ventas**, **Caja**, **Personal** y **Control horario** se encienden con Propinas: la propina va con su
  venta, la de efectivo entra en la caja, es de una persona del equipo y el reparto por horas usa los
  fichajes.
- **Ajustes**: de fábrica, las propinas están **apagadas** (como en Square, SumUp, Revo u Odoo). Se encienden en
  **Propinas → Ajustes** (TIP-F01).
- **Quien atiende**: la propina es de la persona del chip «Atiende» de la cuenta (SALE-F16); con «Yo», de quien
  cobra. Para que cuente para alguien, esa persona tiene que tener ficha en Personal.
- **Moneda**: la del negocio, con sus decimales; un porcentaje se redondea a la unidad más pequeña de la moneda
  (el céntimo en euros, el yen entero en Japón), la mitad hacia arriba.

Configuración inicial, paso a paso:

1. Como administrador, abre **Propinas → Ajustes**, enciende «Pedir propina al cobrar» y revisa las
   sugerencias de cada forma de pago (TIP-F01).
2. Si el negocio reparte las propinas, define el reparto en **Propinas → Reparto** (TIP-F08, TIP-F09) y mira su
   vista previa (TIP-F10). Sin reparto, cada propina es de quien atendió.
3. Haz un cobro de prueba con propina con tarjeta y otro en efectivo, y comprueba en **Caja** las líneas de
   propina (CASH_REGISTER-F18) y en **Propinas** que llevan el nombre de quien atendió.

## Pantallas

Propinas se abre desde el menú **Propinas** y tiene cuatro entradas: **Propinas**, **Reparto**, **Informe** y
**Ajustes**. Quien no puede gestionar ve solo **Mis propinas**.

### Paso «Propina» en el Cobro
Dentro de la hoja **Cobro** de Ventas (SALE-F39), solo con las propinas encendidas: la fila «Propina» con
las tres sugerencias de la forma de pago elegida («3 %», «5 %», «10 %», cada una con su importe debajo),
«Otra cantidad» y «Sin propina»; la marcada de fábrica es «Sin propina». Debajo, «Para <nombre>» (quien
atiende). En efectivo, cuando lo entregado pasa del total, el botón «Quédese el cambio». Con una propina
puesta, el importe grande dice «<total> + <propina> de propina».

### Propinas
Título «Propinas», periodo («Hoy», «7 días», «30 días»), tabla (Fecha, Venta, Para, Forma de pago, Importe,
Estado) con el buscador «Buscar venta o persona…», filtros (persona, forma de pago, estado), vista de tabla o
tarjetas, 50 por página. **+** «Anotar propina» y, por fila, «Ajustar» y «Anular» (solo mientras su día no
está repartido). Arriba, «Declarar propinas del turno» (TIP-F07). Vacía: «Todavía no hay propinas.»;
cargando: «Cargando propinas…».

### Reparto
Las reglas del reparto (TIP-F08, TIP-F09), una tarjeta por regla, con «Vista previa» (TIP-F10) y, debajo, los
días y servicios por aprobar con «Aprobar» (TIP-F11) y los aprobados con «Pagar» (TIP-F12). Sin reglas:
«Sin reparto: cada propina es de quien atendió.».

### Informe
Por persona o por turno (TIP-F13): propinas con tarjeta, en efectivo y declaradas, lo que aportó al bote y lo
que recibió, pagado y pendiente. Exportar en CSV.

### Mis propinas
Las propias, de hoy y de la semana (TIP-F14), con lo pagado y lo pendiente.

### Ajustes
«Pedir propina al cobrar», y por cada forma de pago activa sus tres sugerencias (cada una en «%» o en
importe), cuál sale marcada, «Permitir otra cantidad» y «Guardar».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» (o el texto de su pantalla) mientras llega el primer resultado. |
| Vacío | El texto de su pantalla, con **+** si puede anotar. |
| Error | El aviso con «Reintentar»; un rechazo de una acción sale dentro de su ventana, junto a su campo. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| App inactiva | «Propinas no está activa en este negocio.»; la hoja **Cobro** no pinta el paso. |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Vertical | Estado |
|---|---|---|---|
| TIP-F01 | Configurar las propinas | común | no hecho |
| TIP-F02 | Proponer la propina al cobrar | común | no hecho |
| TIP-F03 | Anotar una propina con tarjeta | común | no hecho |
| TIP-F04 | Anotar una propina en efectivo | común | no hecho |
| TIP-F05 | Echar al bote una propina sin tique | restaurante | no hecho |
| TIP-F06 | Ajustar o anular una propina | común | no hecho |
| TIP-F07 | Declarar las propinas en efectivo al cerrar el turno | restaurante | no hecho |
| TIP-F08 | Definir el reparto | restaurante | no hecho |
| TIP-F09 | Repartir a otro puesto (tip-out) | restaurante | no hecho |
| TIP-F10 | Ver la vista previa del reparto | restaurante | no hecho |
| TIP-F11 | Aprobar el reparto de un día o servicio | restaurante | no hecho |
| TIP-F12 | Pagar las propinas | común | no hecho |
| TIP-F13 | Ver el informe por persona y por turno | común | no hecho |
| TIP-F14 | Ver mis propinas | común | no hecho |

### TIP-F01 Configurar las propinas
<!-- origen: nuevo (hub#562; ficha de Toast, Square, Revo XEF y SumUp) -->
Estado: no hecho — la app no existe todavía (hub#1498)
Vertical: común
Actor: propietario, administrador, asistente
Pantalla: Ajustes
Pasos:
1. Abre **Propinas → Ajustes** y enciende «Pedir propina al cobrar».
2. En cada forma de pago activa (Efectivo, Tarjeta, Bizum…) revisa sus tres sugerencias: cada una es un
   porcentaje («5 %») o un importe («2,00 €»). De fábrica, 3 %, 5 % y 10 % en todas.
3. Elige cuál sale marcada al abrir el cobro (de fábrica, «Sin propina») y si se permite «Otra cantidad».
4. Pulsa «Guardar». Sale «Ajustes guardados.».
Entra: las formas de pago de Ventas.
Sale: los ajustes; el siguiente cobro ya los usa. El porcentaje se calcula sobre el total de la cuenta antes de
descuentos, como en Toast, y se redondea a la unidad de la moneda.
Si falla: una sugerencia vacía, cero, negativa o de más del 100 % se dice debajo de su campo y no se guarda; dos
sugerencias iguales en la misma forma de pago, «Esa sugerencia ya está.». Sin permiso, la pantalla se ve
bloqueada con «No tienes permiso para cambiar estos ajustes.».
Implicados: SALE-F37

### TIP-F02 Proponer la propina al cobrar
<!-- origen: nuevo (hub#562; SALE-G06 del registro de la migración) -->
Estado: no hecho — la app no existe y la hoja Cobro aún no pinta pasos de otras apps (hub#1498, hub#1500)
Vertical: común
Actor: empleado, responsable
Pantalla: Cobro
Pasos:
1. Con las propinas encendidas, pulsa «Cobrar · <total>»: la hoja **Cobro** enseña la fila «Propina» con las
   sugerencias de la forma de pago elegida y su importe debajo.
2. Toca la que dice el cliente, o «Otra cantidad» y teclea el importe, o «Sin propina». Cambiar de forma de pago
   cambia las sugerencias y conserva la elegida si es un importe.
3. El importe grande pasa a «<total> + <propina> de propina» y el botón a «Cobrar <total + propina>».
4. Cobra como siempre (SALE-F01, F02): con tarjeta, TIP-F03; en efectivo, TIP-F04. Con «Repartir el cobro»
   (SALE-F03), la fila sale para cada cobro y cada uno lleva su propina.
Entra: el total de la cuenta, la forma de pago y quien atiende (SALE-F16).
Sale: la venta, igual que sin propina, y la propina guardada con su venta, su forma de pago, su importe y la
persona a quien pertenece (avisa: `tip.tip.added`).
Si falla: una cantidad negativa o ilegible se dice debajo de su campo y no cobra. Si la venta se cobra y la
propina no se guarda (se corta la red), la hoja dice «La venta está cobrada, pero la propina no se ha
guardado.» con «Reintentar»; el reintento no la duplica, y también se puede anotar después (TIP-F03, TIP-F04).
Con quien atiende sin ficha en Personal, la propina se guarda «Sin asignar» y entra en el reparto o se asigna
al ajustarla (TIP-F06).
Implicados: SALE-F39, SALE-F16, CASH_REGISTER-F18

### TIP-F03 Anotar una propina con tarjeta
<!-- origen: nuevo (hub#562; Lightspeed «Add tip», Square «liquidar propinas») -->
Estado: no hecho — la app no existe todavía (hub#1498)
Vertical: común
Actor: empleado, responsable, asistente
Pantalla: Cobro, Propinas
Pasos:
1. En el cobro con tarjeta, con la propina elegida, la hoja dice «Cobra <total + propina> en el datáfono y
   confirma.»: el datáfono cobra la cuenta y la propina juntas.
2. Si el cliente la añade en el datáfono después (o se olvidó en el cobro), en **Propinas** pulsa **+** «Anotar
   propina», elige la venta por su número, «Tarjeta» y el importe que el datáfono cobró de más, y «Guardar».
Entra: la venta y lo que el datáfono cobró de más (ERPlora no habla con el datáfono).
Sale: la propina con tarjeta. En la caja abierta sale como «Propinas con tarjeta», sin tocar el efectivo esperado
(CASH_REGISTER-F18).
Si falla: anotarla sobre una venta anulada o devuelta entera, «Esa venta está anulada: no admite propina.»; sobre
una venta de un día ya repartido, «Ese día ya está repartido: reábrelo para añadir propinas.» (TIP-F11).
Implicados: CASH_REGISTER-F18

### TIP-F04 Anotar una propina en efectivo
<!-- origen: nuevo (hub#562; Revo XEF «convertir el cambio en propina», SumUp «Use for tip») -->
Estado: no hecho — la app no existe todavía (hub#1498)
Vertical: común
Actor: empleado, responsable, asistente
Pantalla: Cobro, Propinas
Pasos:
1. En el cobro en efectivo con propina, lo entregado tiene que cubrir el total más la propina; el cambio es lo
   entregado menos los dos.
2. O, sin propina elegida, marca lo entregado: si sobra, sale «Quédese el cambio». Púlsalo si el cliente deja el
   cambio: la propina es el cambio y el cambio queda en 0.
3. Después del cobro, en **Propinas**, **+** «Anotar propina», la venta, «Efectivo» y el importe.
Entra: la venta, lo entregado y la propina.
Sale: la propina en efectivo, que entra en el cajón: en la caja abierta sale como «Propinas en efectivo» y sube
el esperado (CASH_REGISTER-F18).
Si falla: con «Activar caja» encendido y la caja cerrada, «La caja está cerrada: abre una sesión de caja para
anotar una propina en efectivo.»; lo entregado que no cubre el total más la propina, «Lo entregado no cubre el
total y la propina».
Implicados: SALE-F01, CASH_REGISTER-F18

### TIP-F05 Echar al bote una propina sin tique
<!-- origen: nuevo (hub#562; ficha de Toast, bote del turno) -->
Estado: no hecho — la app no existe todavía (hub#1498)
Vertical: restaurante
Actor: responsable
Pantalla: Propinas
Pasos:
1. Al final del servicio, cuenta el bote de la barra y, en **Propinas**, pulsa **+** «Anotar propina» y elige
   «Al bote, sin tique».
2. Escribe el importe y pulsa «Guardar».
Entra: el importe en efectivo.
Sale: una propina sin venta ni persona, del turno abierto, que entra en el cajón (CASH_REGISTER-F18) y se reparte
con las reglas del día (TIP-F08); sin reglas, queda «Sin asignar» hasta que se asigna (TIP-F06).
Si falla: la caja cerrada, el mismo aviso que TIP-F04.
Implicados: TIP-F08, CASH_REGISTER-F18

### TIP-F06 Ajustar o anular una propina
<!-- origen: nuevo (hub#562; Toast «ajustar propinas de una cuenta cerrada») -->
Estado: no hecho — la app no existe todavía (hub#1498)
Vertical: común
Actor: responsable, asistente
Pantalla: Propinas
Pasos:
1. En la fila de la propina, pulsa «Ajustar»: cambia el importe o la persona y escribe el «Motivo».
2. O pulsa «Anular», escribe el «Motivo» y confirma.
3. Anular o devolver entera una venta anula su propina sola: el cliente recupera lo que pagó, propina incluida.
   Una devolución de solo unas líneas no la toca.
Entra: la propina, el importe o la persona nuevos y el motivo; las anulaciones y devoluciones de Ventas.
Sale: la propina ajustada o anulada, con quién, cuándo y por qué (avisa: `tip.tip.adjusted`, `tip.tip.voided`).
En la caja abierta, la diferencia entra o sale en su forma de pago (CASH_REGISTER-F18): nunca se toca la sesión
ya cerrada.
Si falla: sin motivo, «Escribe el motivo.»; con el día ya repartido, «Ese día ya está repartido: reábrelo para
cambiar sus propinas.».
Implicados: SALE-F30, SALE-F31, CASH_REGISTER-F18

### TIP-F07 Declarar las propinas en efectivo al cerrar el turno
<!-- origen: nuevo (hub#562; Toast «declarar propinas en efectivo») -->
Estado: no hecho — la app no existe todavía (hub#1501)
Vertical: restaurante
Actor: empleado
Pantalla: Propinas
Pasos:
1. Antes de fichar la salida, en **Propinas** pulsa «Declarar propinas del turno».
2. Escribe las propinas en efectivo que recibiste en mano (las que no pasaron por el TPV) y lo que diste a otros
   puestos, y pulsa «Declarar».
3. Si lo declarado queda por debajo del porcentaje mínimo de tus ventas en efectivo que fija el negocio, sale un
   aviso, que no impide declarar.
Entra: la jornada fichada (ATTENDANCE-F01) y las ventas en efectivo de esa persona en el turno.
Sale: la declaración del turno (avisa: `tip.declaration.added`); cuenta en el informe y en el reparto, pero no
entra en la caja: ese dinero no pasó por el cajón.
Si falla: sin una jornada fichada ese día, «No tienes una jornada fichada hoy.»; un importe negativo se dice
debajo de su campo.
Implicados: ATTENDANCE-F01

### TIP-F08 Definir el reparto
<!-- origen: nuevo (hub#562; Toast «Pool Tips and Tipping Out», Square «repartir propinas») -->
Estado: no hecho — la app no existe todavía (hub#1501)
Vertical: restaurante
Actor: responsable, administrador
Pantalla: Reparto
Pasos:
1. En **Propinas → Reparto**, pulsa **+** «Nueva regla».
2. Elige los puestos que aportan y los que reciben (los roles de Personal), qué parte de cada fuente va al bote
   (tarjeta, efectivo, bote), cómo se reparte entre puestos (puntos o %) y entre personas (por horas fichadas o a
   partes iguales), y cada cuánto: día, servicio (comida, cena) o tique.
3. Pulsa «Guardar».
Entra: los roles de Personal (STAFF-F04) y los fichajes (ATTENDANCE-F01).
Sale: la regla (avisa: `tip.rule.created`, `tip.rule.updated`, `tip.rule.deleted`); vale desde ese momento, nunca
hacia atrás.
Si falla: una regla cuyos porcentajes no suman 100, «Los porcentajes tienen que sumar 100.»; un puesto que
aporta y recibe a la vez en la misma regla, «Un puesto no puede aportar y recibir en la misma regla.».
Implicados: STAFF-F04, ATTENDANCE-F01

### TIP-F09 Repartir a otro puesto (tip-out)
<!-- origen: nuevo (hub#562; Toast «tipping out») -->
Estado: no hecho — la app no existe todavía (hub#1501)
Vertical: restaurante
Actor: responsable, administrador
Pantalla: Reparto
Pasos:
1. En una regla, pulsa «Añadir reparto a otro puesto».
2. Elige el puesto que da (camarero), el que recibe (cocina o barra) y qué da: un % de sus ventas o de sus
   propinas. Pulsa «Guardar».
Entra: las ventas y las propinas de cada persona del puesto que da.
Sale: la regla con su reparto a otro puesto, que entra en la vista previa y en el reparto del día.
Si falla: un % de más de 100 o negativo se dice debajo de su campo.
Implicados: TIP-F08

### TIP-F10 Ver la vista previa del reparto
<!-- origen: nuevo (hub#562; ficha de Toast) -->
Estado: no hecho — la app no existe todavía (hub#1501)
Vertical: restaurante
Actor: responsable, administrador
Pantalla: Reparto
Pasos:
1. En una regla, pulsa «Vista previa» y elige un día reciente.
2. Sale, por persona, lo que aportó y lo que recibiría con esa regla, sin guardar nada.
Entra: la regla y las propinas, ventas y fichajes del día.
Sale: nada; enseña.
Si falla: un día sin propinas, «Ese día no tiene propinas.».
Implicados: TIP-F08

### TIP-F11 Aprobar el reparto de un día o servicio
<!-- origen: nuevo (hub#562; ficha de Toast) -->
Estado: no hecho — la app no existe todavía (hub#1501)
Vertical: restaurante
Actor: responsable, administrador, asistente
Pantalla: Reparto
Pasos:
1. En **Reparto**, en el día o servicio por aprobar, revisa lo de cada persona y pulsa «Aprobar».
2. Para corregir algo de un día aprobado, pulsa «Reabrir», corrige y vuelve a aprobar.
Entra: las propinas, declaraciones, ventas y fichajes del día y las reglas vigentes ese día.
Sale: lo de cada persona, fijado (avisa: `tip.pool.settled`, `tip.pool.reopened`). Sin reglas, cada propina ya es
de quien atendió y no hay nada que aprobar.
Si falla: con un fichaje de ese día abierto o por revisar, «Hay jornadas de ese día sin cerrar o por revisar:
corrígelas en Control horario antes de aprobar.» (ATTENDANCE-F05, ATTENDANCE-F08); un día con propinas ya
pagadas no se reabre: «Ese día ya tiene propinas pagadas.».
Implicados: ATTENDANCE-F05, ATTENDANCE-F08

### TIP-F12 Pagar las propinas
<!-- origen: nuevo (hub#562; Square «pagar propinas desde la caja», Toast «tip out») -->
Estado: no hecho — la app no existe todavía (hub#1501)
Vertical: común
Actor: responsable, administrador, asistente
Pantalla: Reparto, Informe
Pasos:
1. En lo pendiente de una persona, pulsa «Pagar».
2. Elige «En efectivo, de la caja» o «Por otra vía» (transferencia, nómina) y confirma.
Entra: lo pendiente de esa persona (aprobado o, sin reparto, sus propias propinas).
Sale: el pago (avisa: `tip.payout.paid`). En efectivo, sale del cajón como «Propinas pagadas» y baja el esperado
(CASH_REGISTER-F18), para que la caja no salga descuadrada.
Si falla: en efectivo con la caja cerrada, «La caja está cerrada: abre una sesión de caja para pagar en
efectivo.»; un pago que dejaría la caja en negativo sin permitirlo, el aviso de Caja (CASH_REGISTER-F05); pagar
más de lo pendiente, «No se puede pagar más de lo pendiente.».
Implicados: CASH_REGISTER-F05, CASH_REGISTER-F18

### TIP-F13 Ver el informe por persona y por turno
<!-- origen: nuevo (hub#562; Square «informe de turno», SumUp «Tips report») -->
Estado: no hecho — la app no existe todavía (hub#1498)
Vertical: común
Actor: responsable, administrador
Pantalla: Informe
Pasos:
1. En **Propinas → Informe**, elige el periodo y «Por persona» o «Por turno» (la jornada fichada).
2. Sale, por persona: propinas con tarjeta, en efectivo y declaradas, lo aportado y lo recibido en el reparto,
   lo pagado y lo pendiente. «Exportar» lo baja en CSV.
Entra: propinas, declaraciones, repartos, pagos y jornadas.
Sale: nada; enseña.
Si falla: el error de carga con «Reintentar».
Implicados: ATTENDANCE-F01

### TIP-F14 Ver mis propinas
<!-- origen: nuevo (hub#562; MyToast) -->
Estado: no hecho — la app no existe todavía (hub#1498)
Vertical: común
Actor: empleado
Pantalla: Mis propinas
Pasos:
1. Abre **Propinas** (quien no gestiona ve directamente **Mis propinas**).
2. Ve las suyas de hoy y de la semana, por forma de pago, lo recibido del reparto, lo pagado y lo pendiente.
Entra: las propinas y pagos de su ficha de Personal.
Sale: nada; enseña.
Si falla: sin ficha de Personal vinculada, «Tu usuario no está vinculado a ninguna ficha de Personal: pide a un
responsable que la vincule en Personal.».
Implicados: STAFF-F03

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto) y la API, con las mismas reglas y
permisos. Una propina se nombra por su venta («la propina de la 20261114-0007») y una persona, por su nombre.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los ajustes de propinas | ver propinas | F01, F02 | `tip.settings.get` |
| Las sugerencias para un cobro: total, forma de pago y su importe | anotar | F02 | `tip.suggestion.get` |
| Las propinas, con búsqueda, filtros y páginas | ver propinas | F03–F06 | `tip.tip.list` |
| Las reglas del reparto | gestionar | F08, F09 | `tip.policy.get` |
| La vista previa del reparto de un día | gestionar | F10 | `tip.policy.preview` |
| El informe por persona y por turno | gestionar | F13 | `tip.report.by_employee`, `tip.report.by_shift` |
| Las propias de quien pregunta | ver propinas | F14 | `tip.report.mine` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Guarda los ajustes | ajustes | F01 | `tip.settings.update` |
| Anota una propina (de una venta o al bote) | anotar | F02–F05 | `tip.tip.add` |
| Ajusta una propina | gestionar | F06 | `tip.tip.update` |
| Anula una propina | gestionar | F06 | `tip.tip.void` |
| Declara las propinas en efectivo del turno | anotar | F07 | `tip.declaration.add` |
| Crea, cambia o borra una regla del reparto | gestionar | F08, F09 | `tip.rule.create`, `tip.rule.update`, `tip.rule.delete` |
| Aprueba o reabre el reparto de un día | gestionar | F11 | `tip.pool.settle`, `tip.pool.reopen` |
| Paga lo pendiente de una persona | gestionar | F12 | `tip.payout.add` |

`tip.pool.settle` y `tip.payout.add` son de riesgo alto: el asistente enseña la vista previa completa antes de
confirmar.

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Ajustes guardados | Guardar los ajustes | Qué cambió | `tip.settings.updated` |
| Propina anotada | Anotarla | La venta, la persona, la forma de pago y el importe | `tip.tip.added` |
| Propina ajustada o anulada | Ajustarla o anularla | Lo de antes, lo nuevo y el motivo | `tip.tip.adjusted`, `tip.tip.voided` |
| Propinas declaradas | Declarar | La persona, el turno y los importes | `tip.declaration.added` |
| Regla creada, cambiada o borrada | Cambiar el reparto | La regla | `tip.rule.created`, `tip.rule.updated`, `tip.rule.deleted` |
| Reparto aprobado o reabierto | Aprobar o reabrir | El día o servicio y lo de cada persona | `tip.pool.settled`, `tip.pool.reopened` |
| Propinas pagadas | Pagar | La persona, el importe y la vía | `tip.payout.paid` |

### A qué reacciona

- `sale.sale.voided` y `sale.sale.refunded` (devolución entera): anula la propina de esa venta (F06).
- `attendance.record.clocked_out` y `attendance.record.corrected`: las pantallas del reparto y del informe se
  refrescan solas.

### Lo que necesita de otras apps

- **Ventas** (requisito): la venta de la propina, quién atendió y sus formas de pago; la hoja **Cobro** pinta el
  paso «Propina» porque Propinas lo declara (SALE-F39), sin que Ventas sepa de propinas.
- **Caja** (requisito): apunta en la sesión abierta lo que entra y sale de propinas (`cash_register.movement.add`,
  CASH_REGISTER-F18).
- **Personal** (requisito): las personas y su rol, para saber de quién es cada propina y repartir por puesto.
- **Control horario** (requisito): las horas fichadas, para el reparto por horas y el informe por turno.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver propinas (las propias el empleado) | sí | sí | sí | sí | `tip.view_tip` |
| Anotar y declarar | sí | sí | sí | sí | `tip.add_tip` |
| Ajustar, anular, reparto, aprobar, pagar e informe | sí | sí | sí | no | `tip.manage` |
| Ajustes | sí | sí | no | no | `tip.manage_settings` |

## Para quien lo mantiene

### Por qué la propina no entra en el tique

La propina **nunca** entra en la base imponible, ni en el IVA, ni en el total del tique o de la factura, ni en
su registro de VeriFactu. En lenguaje llano:

- **El IVA se paga sobre el precio de lo que se vende** (la «contraprestación», art. 78 de la Ley del IVA). La
  propina voluntaria no es precio: es un regalo del cliente al personal, que el negocio solo recoge y entrega.
  Por eso no es base imponible: lo dijo el Tribunal de Justicia de la UE (sentencia de 3 de marzo de 1994,
  asunto C-16/93) y la Dirección General de Tributos lo repite para la hostelería (consultas 2174-03,
  V2604-10 y V1808-22).
- **VeriFactu guarda una copia de cada factura** (su base, su IVA y su total): si la propina entrara en el
  tique, el negocio pagaría IVA por un dinero que no es suyo y el registro no cuadraría con lo que se vendió.
- Para quien la recibe es **sueldo** (rendimiento del trabajo en su IRPF): eso es de la nómina, no de esta app.
- Un **cargo de servicio obligatorio** («servicio 10 %») sí es precio y lleva IVA: no es una propina y esta app
  no lo hace.
- El tope del efectivo (1.000 € en un negocio de España, SALE-F03) mira el total de la venta, como hoy: la
  propina no es parte del precio.

Por eso la propina es una fila propia de esta app, ligada a su venta, y Ventas solo la lleva en el bloque de
pago del papel (SALE-F39), fuera del bloque fiscal.

### Decisiones de plataforma

- **Ventas no conoce a Propinas.** Propinas declara en su `LiveAppConfig` un paso `checkout` (el mismo patrón
  que `setup`, `widgets` y `bell` del Inicio) y Ventas pinta los pasos de las apps activas sin saber cuáles son
  (SALE-F39). El paso de Propinas llama él mismo a `tip.suggestion.get` y `tip.tip.add`.
- **La caja la lleva Caja.** Propinas apunta sus entradas y salidas con `cash_register.movement.add`, marcadas
  como suyas para que Caja las enseñe en su propia línea (CASH_REGISTER-F18).
- **Una propina se anota una sola vez por cobro**: la clave del intento del cobro de Ventas (SALE-F06) la hace
  idempotente; el reintento no la duplica.

### Lo que NO hace, a propósito

- No cobra con el datáfono ni deja que el cliente elija la propina en una pantalla suya: el empleado la marca en
  el TPV (ERPlora no habla con el datáfono).
- No ajusta la autorización de la tarjeta antes del cierre del lote, no retiene la comisión de la tarjeta sobre la
  propina y no paga a una tarjeta del empleado.
- No pone propina en los pedidos en línea (`cart_checkout` no cobra en línea).
- No cobra un cargo de servicio obligatorio (es precio con IVA, ver arriba).
- No reparte por categoría de producto ni por el puesto fichado ese día: manda el rol de la ficha de Personal.
- No imprime sugerencias de propina en la cuenta de la mesa.
- No exporta a nómina: eso es de la etapa ERP.
