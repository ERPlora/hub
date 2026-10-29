# Workbook — Impuestos (app)
Prefijo: TAX
Alcance MVP: transversal
Estado de la app: completa (2026-10-22)
Lo que no entra todavía: ver «Lo que queda fuera».

> Manual de usuario y especificación de la app `tax`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Impuestos del producto actual
> (`modules-workspace/modules/taxes`, `origin/main` `3755bc4`). La app hace lo mismo y se verá igual,
> salvo lo que dice «Cambios frente al producto actual», al final; los números de flujo se conservan
> (`TAXES-Fnn` → `TAX-Fnn`) porque otras apps los citan.

## Para qué sirve y para quién

Impuestos guarda lo que dice cuánto IVA lleva cada cosa que se vende:

- las **categorías fiscales** («Restauración — comida», «Servicio — general»…), a las que apuntan los
  productos de Inventario, los servicios de Servicios, las secciones del precio libre de Ventas, los menús
  y las opciones de suplemento que tributan aparte;
- las **reglas**, que fijan el tipo de cada categoría en un país o una región y entre unas fechas, con
  su calificación fiscal (sujeta, exenta, no sujeta, con inversión del sujeto pasivo);
- los **alias**, textos de fuera («comida», «beer», «IVA 10») que el importador de Inventario reconoce
  como una categoría.

Casi nadie lo abre a diario: se prepara al montar el negocio y se toca cuando cambia un tipo. Pero
cada línea que cobra Ventas, cada factura de Facturación y cada producto de Inventario o Servicios
lee de aquí. Sirve igual a la restauración y a la peluquería: lo que cambia es qué categorías vende
cada una, no cómo funciona.

Quién la usa:

- El **propietario**, el **administrador** y el **responsable** crean categorías, reglas y alias, ponen
  fecha de fin a una regla y la desactivan o reactivan.
- El **empleado** solo consulta y calcula.

No decide el precio, no emite facturas ni habla con la AEAT, y no guarda el país del negocio.

## Referencia adoptada

- [Ley 37/1992 del IVA](https://www.boe.es/buscar/act.php?id=BOE-A-1992-28740): tipos general,
  reducido y superreducido (arts. 90 y 91), exenciones (art. 20) y recargo de equivalencia. Los tipos
  de fábrica salen de aquí; su contraste con la asesoría es de cada negocio.
- Las listas de la AEAT (régimen `ClaveRegimen`, exención `OperacionExenta`, causas E1…E6) viajan como
  códigos opacos: Impuestos los guarda y los devuelve, no los interpreta.
- Odoo y Square: el impuesto se asigna al producto **por categoría**, no por un porcentaje suelto;
  varios impuestos sobre la misma línea; precio con el impuesto incluido o añadido.
- Cambiar un tipo = poner fecha de fin al vigente y crear el nuevo, nunca editar la regla (Oracle
  E-Business Tax, Dynamics 365 y SAP). Ninguno deja dos tipos vigentes el mismo día para lo mismo.

## Antes de empezar

- Al activar Impuestos, el negocio recibe de fábrica **11 categorías**, **18 alias** y **los tipos de
  España** (TAX-F16). Con eso un negocio español puede vender sin tocar nada.
- Activar Inventario, Servicios, Ventas, Facturación, Menús y combos o Suplementos activa Impuestos con
  ellas, e Impuestos no se puede desactivar mientras alguna de ellas esté activa.
- **País y territorio fiscal del negocio**: el país es el de la cuenta de ERPlora del negocio (en la fase 1,
  España para todos); el territorio fiscal —todo el país, Canarias, Ceuta o Melilla— se elige en
  **Impuestos → Ajustes** (TAX-F11). Ventas, Facturación, las pantallas y el asistente calculan con los
  dos mientras no se pregunte por otro país.
- Las reglas de fábrica son solo de España. Un negocio de otro país (cuando la cuenta de ERPlora lo traiga)
  tendrá que crear las suyas (TAX-F04); ni el aviso «Tus impuestos» ni el paso del Inicio (TAX-F17) lo
  detectan todavía, porque cuentan las reglas de cualquier país.
- **«Hoy» es la hora de Madrid** en la fase 1: Impuestos todavía no usa la zona horaria del negocio.
  El día en que cambia un tipo (TAX-F07) empieza a medianoche de Madrid; en Canarias (TAX-F11), una
  hora antes de su medianoche. Cuando use la del negocio, «hoy» será el suyo.

Configuración inicial, paso a paso:

1. Abre **Impuestos → Categorías** y revisa que están las que vendes; crea las que falten (TAX-F02).
2. Abre **Impuestos → Reglas** y comprueba que cada categoría tiene su tipo para tu país (TAX-F03).
   Crea las que falten (TAX-F04); si el negocio es de Canarias, Ceuta o Melilla, sigue TAX-F11.
3. Si el negocio es de Canarias, Ceuta o Melilla, elige su territorio en **Impuestos → Ajustes**
   (TAX-F11).
4. Haz una venta de prueba y comprueba el desglose del tique.

## Pantallas

Impuestos se abre desde el menú **Impuestos** y tiene cuatro pestañas en la barra de abajo:
**Categorías**, **Reglas**, **Alias** y **Ajustes**. Mientras ningún tipo esté vigente, las tres primeras llevan arriba el
aviso «Tus impuestos» para quien puede gestionarlos, el mismo paso que trae el Inicio en «Termina de configurar tu
negocio» (TAX-F17). Todas siguen el permiso de quien mira: con solo consulta
sale el aviso «Puedes consultar las reglas fiscales pero no modificarlas.», desaparece el botón **+** y,
en Reglas, las acciones de fila. La app exige el permiso en cada acción aunque la pantalla enseñe el
botón.

### Categorías
Tabla con Clave, Nombre, Descripción, Origen («Sistema» o «Propia»), Activa y el tipo vigente en el
país del negocio («21,00 %», «Exenta»…). Buscador «Buscar clave o nombre…» (clave, nombre y descripción,
guardados o traducidos), filtros por columna (Clave, Nombre, Descripción y Origen) y orden por cualquier
columna; 50 por página, ordenadas por clave de entrada. Las de fábrica salen con su nombre en el idioma
de la persona; las propias, con el texto que se tecleó. Botón **+** que abre el panel de alta (Clave,
Nombre, Descripción, «Añadir»). Sin acciones de fila.

### Reglas
Tabla con Categoría, País, Región, %, Tipo, Calificación (con la causa de exención si la hay), Vigente
desde, Vigente hasta y Activa. Un componente (el recargo) sale justo debajo de su regla raíz, como
«↳ etiqueta». Buscador «Buscar categoría o país…» y filtros de País, Región, Categoría, Tipo,
Calificación, Régimen, % (desde–hasta) y Estado («Activas», «Desactivadas», «Todas»; de entrada,
«Activas»); orden por cualquier columna. Botón **+** con el
panel de alta (País, Región, Categoría, %, Tipo, Calificación, Causa de exención —solo si es exenta—,
Régimen, Vigente desde, Vigente hasta, «Regla raíz (componente de)», «Etiqueta componente» y
«Añadir»). Acciones de fila: «Poner fecha de fin» y «Desactivar»; en una desactivada, «Reactivar».

### Alias
Tabla con Alias, Categoría, Origen («De fábrica» o «Aprendido») y Activa. Buscador «Buscar alias o
categoría…», filtros de Alias, Categoría y Origen y orden por cualquier columna. Botón **+** con el
panel de alta (Alias, Categoría, Origen —«Aprendido» de entrada—, «Añadir»).

### Ajustes
«Territorio fiscal del negocio»: el «País» del negocio, solo de lectura («Es el país de tu cuenta de
ERPlora.»), y el desplegable «Territorio fiscal» con «Todo el país (IVA)», «Canarias (IGIC)», «Ceuta
(IPSI)» y «Melilla (IPSI)», con su explicación debajo, y «Guardar» («Territorio fiscal guardado.»).
Quien solo consulta impuestos ve el territorio sin poder cambiarlo («Puedes ver el territorio fiscal,
pero no cambiarlo.»). Es la pantalla de TAX-F11.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado; en Ajustes, «Cargando los ajustes de impuestos…». |
| Vacío | «Sin categorías fiscales.», «Sin reglas fiscales.» o «Sin alias de categorías.» (o «Sin resultados» con búsqueda o filtro), con **+** si puede crear. |
| Error | El aviso de la tabla con «Reintentar»; un rechazo del alta sale dentro del panel, junto a su campo. En Ajustes, «No se pudieron cargar los ajustes de impuestos.» con «Reintentar» (sin enseñar ningún territorio como el del negocio), y un rechazo al guardar, «No se pudo guardar el territorio fiscal.» con el motivo bajo «Territorio fiscal». |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| Sin tipos vigentes | Para quien puede gestionar, el aviso «Tus impuestos» con «Configurar» (TAX-F17). |
| App inactiva (`app_inactive`) | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| TAX-F01 | Ver las categorías fiscales | hecho |
| TAX-F02 | Crear una categoría fiscal propia | hecho |
| TAX-F03 | Ver y filtrar las reglas | hecho |
| TAX-F04 | Fijar el tipo de una categoría en un país o región | hecho |
| TAX-F05 | Declarar una operación exenta, no sujeta o con inversión del sujeto pasivo | hecho |
| TAX-F06 | Añadir un recargo de equivalencia a un tipo | hecho |
| TAX-F07 | Cambiar un tipo a partir de una fecha | hecho |
| TAX-F08 | Desactivar y reactivar una regla | hecho |
| TAX-F09 | Reparar una regla que cobra un tipo donde no toca | descartado |
| TAX-F10 | Resolver reglas que se solapan | descartado |
| TAX-F11 | Montar un negocio de Canarias, Ceuta o Melilla | hecho |
| TAX-F12 | Crear varias reglas de golpe | hecho |
| TAX-F13 | Ver los alias de categoría | hecho |
| TAX-F14 | Enseñar un alias de categoría a mano | hecho |
| TAX-F15 | Decir al importador de Inventario qué categoría es un texto | hecho |
| TAX-F16 | Sembrar el catálogo de fábrica al activar | hecho |
| TAX-F17 | Avisar de que faltan tipos para el país del negocio | hecho |
| TAX-F18 | Calcular el impuesto de un importe | hecho |
| TAX-F19 | Entregar las reglas y las categorías a Ventas, Facturación, Inventario y Servicios | hecho |

### TAX-F01 Ver las categorías fiscales
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f04 fi:modules/taxes#permission-role_permissions fi:modules/taxes#query-taxes-categories-list old:taxes/WORKFLOW.md#taxes-f01 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Categorías
Pasos:
1. Abre **Impuestos → Categorías**.
2. Busca por clave o nombre, o filtra por Origen («Sistema» o «Propia»).
3. Lee la Clave: es lo que guardan los productos y los servicios y no cambia nunca; el Nombre es solo
   una etiqueta. La columna del tipo dice qué se cobra hoy en el país del negocio.
Entra: nada; lee las categorías y las reglas vigentes hoy.
Sale: nada (solo lectura). El nombre de una categoría de fábrica sale en el idioma de quien mira; una
propia, con su texto. La búsqueda encuentra lo que se ve: «comida» encuentra «Restauración — comida».
Si falla: el aviso de la tabla con «Reintentar». Sin permiso de consulta, «No tienes permiso».
Implicados: COMBO-F02, INVENTORY-F01, INVENTORY-F02, INVENTORY-F05, INVENTORY-F06, MODIFIER-F04, SALE-F01,
SALE-F35, SERVICE-F01

### TAX-F02 Crear una categoría fiscal propia
<!-- origen: fi:modules/taxes#command-taxes-categories-create old:taxes/WORKFLOW.md#taxes-f02 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Categorías
Pasos:
1. En Categorías pulsa **+**.
2. Escribe la Clave (minúsculas; empieza por letra; letras, dígitos, puntos y guiones bajos; hasta 80;
   por ejemplo `product.books`) y el Nombre; la Descripción es opcional.
3. Pulsa «Añadir». El panel se cierra y la categoría sale en la tabla como «Propia».
Entra: clave, nombre y descripción que escribe la persona.
Sale: la categoría, única por clave en el negocio; Impuestos avisa de que hay una categoría nueva
(`tax.category.created`). No trae ninguna regla: hasta que se cree una (TAX-F04), una venta de esa
categoría se rechaza. Inventario también la crea cuando alguien elige «Crear» al importar un fichero
(TAX-F15).
Si falla: una clave con otra forma o un nombre vacío salen debajo de su campo; una clave que ya existe,
«Ya hay una categoría fiscal con esa clave.» debajo de la Clave. No se guarda nada.
Implicados: INVENTORY-F09

### TAX-F03 Ver y filtrar las reglas
<!-- origen: fi:modules/taxes#query-taxes-rules-by_country fi:modules/taxes#query-taxes-rules-list old:taxes/WORKFLOW.md#taxes-f03 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Reglas
Pasos:
1. Abre **Impuestos → Reglas**: salen las activas.
2. Busca por categoría o país, o filtra por País, Región, Categoría, Tipo o Calificación.
3. Elige Estado «Desactivadas» (o «Todas») para ver las desactivadas; su fila ofrece «Reactivar»
   (TAX-F08).
4. Reconoce un componente (recargo) porque sale justo debajo de su regla raíz.
Entra: nada; lee las reglas del negocio.
Sale: nada (solo lectura).
Si falla: el aviso de la tabla con «Reintentar».
Implicados: ninguno

### TAX-F04 Fijar el tipo de una categoría en un país o región
<!-- origen: fi:modules/taxes#command-taxes-rules-create old:taxes/WORKFLOW.md#taxes-f04 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Reglas
Pasos:
1. En Reglas pulsa **+**.
2. Escribe el País y elígelo de la lista que sale debajo (lista cerrada ISO 3166-1) y, solo si el tipo
   cambia dentro del país, la Región (por ejemplo ES-CN, que tiene que ser de ese país); vacía vale para
   todo el país.
3. Escribe parte del nombre de la Categoría, elígela de la lista y escribe el %, entre 0 y 100 (hasta
   dos decimales).
4. Elige el Tipo («IVA» de entrada; «IGIC (Canarias)», «IPSI (Ceuta/Melilla)»…) y, si quieres, Vigente
   desde y Vigente hasta (vacío = desde siempre / para siempre). Por el asistente o la API, una regla sin
   Tipo lleva el de su territorio: IGIC en ES-CN, IPSI en ES-CE y ES-ML, IVA en el resto.
5. Pulsa «Añadir»; el panel se cierra y la regla sale en la tabla.
Entra: país, región, categoría, %, tipo y fechas que elige la persona.
Sale: la regla activa; Impuestos avisa (`tax.rule.created`). Desde ese momento Ventas y Facturación la
usan para las ventas nuevas: gana la regla de la región del negocio y, si no hay, la del país entero,
salvo en Canarias, Ceuta y Melilla, donde solo vale la de su territorio (el IVA nacional no se aplica
allí); una regla de otra región nunca se usa. Las ventas ya hechas no cambian (TAX-F07).
Si falla: dos reglas activas de la misma categoría, país y región no pueden estar vigentes el mismo
día: el rechazo sale en «Vigente desde» con «Se solapa con otra regla activa de este país, región y
categoría…» (se resuelve con TAX-F07 o TAX-F08). Un país que no existe, una región de otro país, un %
fuera de 0–100, un «Vigente hasta» anterior a «Vigente desde» o una categoría que no existe salen
debajo de su campo. Una regla del mismo país, región y categoría que empieza el mismo día que otra ya
guardada, aunque esté desactivada: «Ya hay una regla de este país, región y categoría desde ese día,
quizá desactivada: reactívala o empieza esta otro día.», en «Vigente desde». No se guarda nada.
Implicados: INVOICE-F01, SALE-F01

### TAX-F05 Declarar una operación exenta, no sujeta o con inversión del sujeto pasivo
<!-- origen: old:taxes/WORKFLOW.md#taxes-f05 wf:cadena-fiscal#rec_fiscal-f04 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Reglas
Pasos:
1. En Reglas pulsa **+** y rellena país, categoría y tipo como en TAX-F04.
2. En Calificación elige «Exenta», «No sujeta», «No sujeta (reglas de localización)» o «Inversión del
   sujeto pasivo». El % se pone en 0 y se bloquea, con la nota «Esta operación no lleva impuesto, así
   que su tipo es 0 %.».
3. Si es «Exenta», escribe la Causa de exención (hasta 10 caracteres, por ejemplo E1); el Régimen es
   opcional (vacío = el general, 01).
4. Pulsa «Añadir».
Entra: calificación, causa de exención y régimen (códigos de la AEAT, opacos para esta app).
Sale: la regla con su calificación (`tax.rule.created`). La causa se guarda en mayúsculas y solo en una
regla exenta. Facturación toma la calificación de la regla vigente al emitir y VeriFactu la traduce
al registro de la AEAT.
Si falla: una calificación que no cobra impuesto con un % mayor que 0 sale debajo del % («Esta
operación no lleva impuesto: su tipo tiene que ser 0 %.») y no se guarda nada.
Implicados: INVOICE-F01

### TAX-F06 Añadir un recargo de equivalencia a un tipo
<!-- origen: old:taxes/WORKFLOW.md#taxes-f06 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Reglas
Pasos:
1. Crea antes la regla principal de la categoría (TAX-F04): es la raíz.
2. En Reglas pulsa **+**, elige el mismo País, Región y Categoría y escribe el % del recargo (por
   ejemplo 5,2).
3. Elige el Tipo «Recargo»; en «Regla raíz (componente de)» elige la raíz y escribe la «Etiqueta
   componente» (por ejemplo «Recargo de equivalencia»).
4. Pulsa «Añadir».
Entra: el recargo, la raíz de la que cuelga y su etiqueta.
Sale: la regla componente (`tax.rule.created`). Las ventas de esa categoría llevan el tipo combinado
(21 + 5,2 = 26,2) con el desglose por componente; la calificación y la familia de impuesto siguen
siendo las de la raíz.
Si falla: «No se ha podido crear el componente: tiene que colgar de una regla raíz con el mismo país,
región y categoría, y una raíz que no cobra impuesto no admite componentes con tipo.», debajo de la
regla raíz. Un componente de un componente no existe: solo hay un nivel.
Implicados: INVOICE-F01, SALE-F01

### TAX-F07 Cambiar un tipo a partir de una fecha
<!-- origen: wf:cadena-fiscal#rec_fiscal-f02 wf:cadena-fiscal#rec_fiscal-f10 old:taxes/WORKFLOW.md#taxes-f07 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Reglas
Pasos:
1. En la fila de la regla vigente pulsa «Poner fecha de fin».
2. Escribe el último día que se aplica (el día antes de que empiece el tipo nuevo) y pulsa «Guardar
   fecha de fin».
3. Crea la regla nueva (TAX-F04) con «Vigente desde» el día siguiente.
4. La tabla enseña las dos con sus fechas; desde el día del cambio las ventas nuevas usan la nueva.
Entra: la fecha de fin (incluida) y los datos de la regla nueva.
Sale: la regla con su fecha de fin (`tax.rule.ended`). Una venta ya hecha conserva su tipo: la línea de
venta guarda su copia. Una factura ya emitida no cambia. Una regla no se edita: no existe esa acción.
Si falla: un fin anterior al inicio de la regla: «Esa regla no puede terminar antes del día en que
empieza.»; un fin que invade otra regla activa del mismo hueco, el aviso de solape. Dos tramos
seguidos (uno acaba el 31/12, el otro empieza el 1/1) no se solapan. Un fin en el pasado deja un hueco
sin tipo: las ventas de esa categoría se rechazan hasta crear la siguiente.
Implicados: INVOICE-F01, INVOICE-F04, SALE-F01

### TAX-F08 Desactivar y reactivar una regla
<!-- origen: fi:modules/taxes#command-taxes-rules-deactivate old:taxes/WORKFLOW.md#taxes-f08 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Reglas
Pasos:
1. En la fila pulsa «Desactivar» y confirma en «Desactivar regla fiscal» con «Desactivar regla» («La
   regla dejará de aplicarse a operaciones nuevas. Los documentos fiscales ya emitidos no se
   modifican.»).
2. La regla desaparece de la tabla; para verla, elige Estado «Desactivadas».
3. Para recuperarla, en esa vista pulsa «Reactivar» (sin confirmación).
Entra: la regla elegida.
Sale: la regla inactiva o activa (`tax.rule.deactivated` / `tax.rule.activated`). Su %, su país, su
categoría, sus fechas y sus componentes no cambian. Desactivar una raíz deja de aplicar también sus
componentes; si era la única raíz de la categoría, las ventas de esa categoría se rechazan. No existe
borrar una regla.
Si falla: una regla que ya no existe: «Esta regla ya no existe.»; desactivar una ya desactivada o
reactivar una ya activa: «Esa regla ya está desactivada.» / «Esa regla ya está activa.»; reactivar
una que ahora se solapa con otra activa, el aviso de solape.
Implicados: SALE-F01

### TAX-F09 Reparar una regla que cobra un tipo donde no toca
<!-- origen: wf:cadena-fiscal#rec_fiscal-f09 old:taxes/WORKFLOW.md#taxes-f09 -->
Estado: descartado — en el producto actual servía para arreglar reglas guardadas antes de que se prohibieran; aquí ninguna puerta (pantalla, API, lote ni asistente) deja crear una regla que no cobra impuesto con un %, ni un componente con tipo bajo ella, así que no hay nada que reparar
Actor: propietario, administrador, responsable
Pantalla: Reglas
Pasos:
1. Quien guarda una regla exenta, no sujeta o con inversión del sujeto pasivo con un % mayor que 0 ve el
   rechazo debajo del % (TAX-F05).
2. Quien cuelga un componente con tipo de una raíz que no cobra impuesto ve el rechazo debajo de la regla
   raíz (TAX-F06).
Entra: nada.
Sale: nada: la regla incoherente no llega a guardarse.
Si falla: no aplica.
Implicados: ninguno

### TAX-F10 Resolver reglas que se solapan
<!-- origen: old:taxes/WORKFLOW.md#taxes-f10 -->
Estado: descartado — aquí ninguna puerta deja que dos reglas activas del mismo país, región y categoría estén vigentes el mismo día, tampoco si dos personas guardan a la vez: el solape se resuelve antes de guardar, con TAX-F07 o TAX-F08
Actor: propietario, administrador, responsable
Pantalla: Reglas
Pasos:
1. Quien guarda una regla que se solaparía con otra activa del mismo país, región y categoría ve el
   rechazo en «Vigente desde» (TAX-F04).
2. Pone fecha de fin a la vigente (TAX-F07) o la desactiva (TAX-F08) y vuelve a guardar la nueva.
Entra: nada.
Sale: nada: el solape no llega a guardarse.
Si falla: no aplica.
Implicados: ninguno

### TAX-F11 Montar un negocio de Canarias, Ceuta o Melilla
<!-- origen: wf:cadena-fiscal#rec_fiscal-f04 old:taxes/WORKFLOW.md#taxes-f11 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Ajustes y Reglas
Pasos:
1. En **Impuestos → Ajustes** elige el «Territorio fiscal» del negocio: «Canarias (IGIC)», «Ceuta
   (IPSI)» o «Melilla (IPSI)», y pulsa «Guardar»: sale «Territorio fiscal guardado.». El «País» es el
   de la cuenta de ERPlora del negocio.
2. En Reglas crea una regla por cada categoría que vendes: País «España», la Región (ES-CN Canarias,
   ES-CE Ceuta o ES-ML Melilla), el % del territorio y el Tipo «IGIC (Canarias)» o «IPSI
   (Ceuta/Melilla)» (TAX-F04).
3. Crea una regla del territorio por cada categoría que vendas: en Canarias, Ceuta y Melilla el IVA
   nacional no se aplica nunca, así que una categoría sin regla de su territorio no se puede cobrar hasta
   que la tenga. Las reglas del IVA no hace falta borrarlas: vuelven a usarse con «Todo el país (IVA)».
4. Haz una venta de prueba: el tique y su desglose dicen el impuesto del territorio («IGIC 7 %»), y la
   factura lo declara igual.
Entra: el territorio fiscal del negocio y un tipo regional por categoría que fija la persona (no se
siembra ninguno a propósito).
Sale: el territorio guardado, que desde ese momento usan todas las ventas, las facturas, el cálculo de
TAX-F18 y el tipo que enseñan Categorías y las secciones de Ventas: solo cuenta la regla del territorio
(la nacional, de IVA, nunca) y la familia del impuesto (IGIC, IPSI) es la de la regla. Una línea sin categoría ni regla —un
tipo escrito a mano en una factura, o una venta cuya regla ya no existe— se declara con el impuesto de su
territorio: IGIC en Canarias, IPSI en Ceuta y Melilla, IVA en el resto (la de una venta, el territorio con
que se cobró). Evento `tax.settings.updated`, que vuelve a calcular la caja abierta.
Si falla: un territorio que no tiene impuestos propios en el país del negocio se rechaza bajo
«Territorio fiscal» («Esta región no tiene impuestos propios en el país de tu negocio: elige uno de sus
territorios fiscales, o ninguno.»); una categoría sin regla de su territorio no se cobra nunca al IVA
nacional, igual que una categoría sin ninguna regla: el TPV no deja cobrarla («… no se puede cobrar:
ninguna regla fiscal se aplica aquí a su categoría fiscal …»), la factura la rechaza debajo de su línea
(«Ninguna regla fiscal se aplica hoy a la categoría fiscal …») y Categorías y las secciones de Ventas no le
enseñan tipo; se arregla creando su regla (paso 2). Con «Todo el
país (IVA)», las reglas regionales no se usan nunca. Quien solo consulta impuestos ve el
territorio, pero no lo cambia.
Implicados: INVOICE-F01, INVOICE-F03, SALE-F01

### TAX-F12 Crear varias reglas de golpe
<!-- origen: fi:modules/taxes#command-handler-wasm-taxes-rules-bulk_create-bulk_create_rules old:taxes/WORKFLOW.md#taxes-f12 -->
Estado: hecho
Actor: propietario, administrador, responsable (por el asistente o por la API con su sesión; una llave de API no llega)
Pantalla: ninguna (API)
Pasos:
1. Se envían hasta 100 reglas raíz de una vez (por ejemplo, «los tipos de IVA de España 2026»).
2. Cada regla pasa las mismas comprobaciones que una sola (TAX-F04, TAX-F05), también el solape con las
   demás del mismo envío.
3. Si todas valen, se guardan todas; si alguna falla, no se guarda ninguna y la respuesta dice qué
   regla falló y por qué.
Entra: la lista de reglas.
Sale: las reglas creadas; un `tax.rule.created` por cada una.
Si falla: cada rechazo lleva la posición de la regla (`rules.3.rate_pct`…). Los componentes no van por
lote: se crean de uno en uno (TAX-F06), porque necesitan su raíz ya guardada.
Implicados: ninguno

### TAX-F13 Ver los alias de categoría
<!-- origen: fi:modules/taxes#query-taxes-aliases-list old:taxes/WORKFLOW.md#taxes-f13 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Alias
Pasos:
1. Abre **Impuestos → Alias**.
2. Busca por alias o categoría, o filtra por Categoría u Origen.
Entra: nada; lee los alias del negocio.
Sale: nada (solo lectura).
Si falla: el aviso de la tabla con «Reintentar».
Implicados: ninguno

### TAX-F14 Enseñar un alias de categoría a mano
<!-- origen: fi:modules/taxes#command-taxes-aliases-create old:taxes/WORKFLOW.md#taxes-f14 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Alias
Pasos:
1. En Alias pulsa **+**.
2. Escribe el Alias (el texto que llega de fuera, por ejemplo `comida`), escribe parte del nombre de
   la Categoría y elígela de la lista, y elige el Origen («Aprendido» de entrada).
3. Pulsa «Añadir».
Entra: el texto externo, la categoría y el origen que elige la persona.
Sale: el alias, guardado en minúsculas y sin espacios de sobra, único en el negocio
(`tax.alias.created`). La próxima importación de Inventario lo entiende, se escriba como se escriba.
Si falla: un alias que ya existe: «Ese alias ya existe.» debajo del Alias; una categoría que no existe,
debajo de la Categoría. No se guarda nada.
Implicados: INVENTORY-F09

### TAX-F15 Decir al importador de Inventario qué categoría es un texto
<!-- origen: fi:modules/taxes#query-taxes-aliases-resolve old:taxes/WORKFLOW.md#taxes-f15 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Quien importa un fichero de productos con una columna de IVA o de categoría no hace nada en
   Impuestos.
2. Inventario pregunta por cada texto. Impuestos lo pasa a minúsculas y sin espacios de sobra y lo
   contrasta, por este orden, con las claves de las categorías, con sus nombres (también los
   traducidos al español y al inglés) y con los alias.
3. Lo que no casa lo pregunta Inventario a la persona; su respuesta se guarda como alias aprendido o
   como categoría nueva (TAX-F02, TAX-F14).
Entra: el texto, de Inventario.
Sale: la clave de la categoría y por qué casó (clave, nombre o alias), o nada.
Si falla: un texto que no casa devuelve «nada», nunca una categoría parecida.
Implicados: INVENTORY-F09, INVENTORY-F10

### TAX-F16 Sembrar el catálogo de fábrica al activar
<!-- origen: qa:verticals/beauty/00-signup-and-blueprint-beauty qa:verticals/restaurant/00-signup-and-blueprint wf:alta#rec_alta-f08 old-hub:HUB-F22 fi:modules/taxes#seed-bloque old:taxes/WORKFLOW.md#taxes-f16 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. La primera vez que el negocio activa Impuestos (o al nacer con un vertical que lo trae), la app
   siembra el catálogo; no se hace nada a mano.
2. Se comprueba en Categorías y Reglas.
Entra: nada.
Sale: 11 categorías de sistema (`restaurant.food`, `restaurant.drink`, `restaurant.alcohol`,
`restaurant.delivery`, `retail.alcohol`, `service.generic`, `service.health`, `service.education`,
`product.generic`, `product.reduced`, `product.super_reduced`), 18 alias de fábrica y 11 reglas de
España, para todo el país y desde el 01/09/2012: 21 % (`product.generic`, `service.generic`,
`retail.alcohol`), 10 % (`restaurant.food`, `restaurant.drink`, `restaurant.alcohol`,
`restaurant.delivery`, `product.reduced`), 4 % (`product.super_reduced`) y exentas con causa E1 al
0 % (`service.health`, `service.education`). Las bebidas alcohólicas servidas para consumir en el local
son hostelería, al 10 % (art. 91.Uno.2.2º de la Ley 37/1992): `restaurant.alcohol`; las que se venden
para llevar o a domicilio, al 21 %: `retail.alcohol` (alias `takeaway_beer` y `takeaway_wine`). No hay
reglas de IGIC, IPSI, recargo ni de ningún otro país: un tipo inventado se declararía.
Si falla: nunca pisa una fila que ya existe ni duplica nada.
Implicados: ninguno

### TAX-F17 Avisar de que faltan tipos para el país del negocio
<!-- origen: old:taxes/WORKFLOW.md#taxes-f17 wf:alta#rec_alta-f09 old-hub:HUB_SHELL-F27 gh:taxes#19 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Inicio, Categorías, Reglas y Alias
Pasos:
1. En el **Inicio**, mientras ninguna regla raíz activa esté vigente hoy, «Termina de configurar tu negocio»
   trae «Tus impuestos» («Configura los tipos de IVA del país en el que vendes para que el TPV pueda calcular
   el precio de una venta.»), «Importante», a quien puede gestionar impuestos. «Configurar» lleva a la
   pestaña **Reglas** de Impuestos.
2. Abre **Impuestos**: mientras tanto, arriba de Categorías, Reglas y Alias sale el mismo aviso «Tus
   impuestos», solo para quien puede gestionar impuestos.
3. Pulsa «Configurar»: lleva a la pestaña Reglas, donde se crea la que falta con **+** (TAX-F04). En
   Reglas el aviso no lleva botón.
4. En cuanto una regla raíz activa está vigente hoy, el aviso desaparece solo y el paso del Inicio queda
   «Hecho» sin recargar.
Entra: las reglas de cualquier país (ni el aviso ni el paso miran todavía el del negocio).
Sale: cuántas reglas aplican hoy y si los impuestos están configurados. No bloquea vender por sí mismo. Si
la última regla vigente termina (TAX-F07) o se desactiva (TAX-F08), el paso del Inicio vuelve a pendiente
solo, y al reactivarla (TAX-F08) o crear otra (TAX-F04, TAX-F12) vuelve a «Hecho». Cambiar el territorio
fiscal (TAX-F11) no lo mueve.
Si falla: basta una sola regla de cualquier categoría para darlo por hecho. Hoy cuenta las reglas de
cualquier país y de cualquier territorio: un negocio de Canarias sin ninguna regla de IGIC no ve el aviso,
aunque el TPV le explica el motivo al cobrar y la ayuda de Ajustes lo dice (TAX-F11). Una regla exenta o
de IGIC también cuenta: un negocio que solo vende servicios exentos está bien configurado.
Implicados: BASE-F01

### TAX-F18 Calcular el impuesto de un importe
<!-- origen: wf:cadena-fiscal#rec_fiscal-f04 fi:modules/taxes#command-handler-wasm-taxes-calculate-calculate_tax old-hub:HUB-F18 old:taxes/WORKFLOW.md#taxes-f18 qa:modules/taxes/vat-rates-and-breakdown -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario (por el asistente o por la API con su sesión; una llave de API no llega)
Pantalla: ninguna (API)
Pasos:
1. Se indica el importe (en céntimos), la categoría y, si hace falta, el país, la región, la fecha y si
   el importe ya lleva el impuesto.
2. Se obtiene la base, la cuota, el total, el tipo combinado, la calificación, la regla aplicada y el
   desglose por componente.
Entra: importe en céntimos, categoría, país (de entrada, el del negocio con su territorio fiscal,
TAX-F11), región y fecha (de entrada, hoy; en la fase 1, hoy en Madrid). Si se dice un país, se
calcula en ese país y en la región que se diga, sin el territorio del negocio.
Sale: solo la respuesta; no guarda nada ni avisa. Sin el impuesto incluido, la cuota de cada componente
es base × tipo redondeada al céntimo, la mitad hacia arriba. Con el impuesto incluido, la base es el
importe ÷ (1 + tipo combinado) redondeada y la cuota es lo que resta, así que lo cobrado no se mueve un
céntimo (el último componente absorbe el ajuste). Es el mismo cálculo con el que Ventas cierra el tique
y Facturación cuadra la cuota.
Si falla: sin regla aplicable, «Ninguna regla fiscal se aplica a esta categoría en este país.»; nunca
se cobra un 0 % supuesto, salvo que quien pregunta lo pida expresamente (y entonces, con el impuesto
de su territorio: IGIC en Canarias, IPSI en Ceuta y Melilla). Sin importe o sin categoría,
debajo de su campo. Si las reglas no se pueden leer, el cálculo se detiene sin adivinar.
Implicados: INVOICE-F01, INVOICE-F03, SALE-F01, SALE-F09

### TAX-F19 Entregar las reglas y las categorías a Ventas, Facturación, Inventario y Servicios
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 qa:verticals/restaurant/03-menu-and-prices wf:cadena-fiscal#rec_fiscal-f02 qa:verticals/restaurant/07-payment-and-fiscal wf:cadena-fiscal#rec_fiscal-f01 fi:modules/taxes#event-emit-taxes-category-created-taxes-rule-created-taxes-rule-deactivated-taxes-alias-created-declarados-taxes-rule-created-taxes-rules-bulk_create-report-emitidos-por-el-wasm-bulk fi:modules/taxes#query-taxes-categories-get old:taxes/WORKFLOW.md#taxes-f19 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Quien cobra un tique, emite una factura o guarda un producto no abre Impuestos.
2. Ventas y Facturación resuelven el tipo de cada línea con el mismo cálculo de TAX-F18, dentro de su
   propia operación: si las reglas no se pueden leer, la operación se rechaza antes de escribir nada.
3. Inventario, Servicios, Ventas (sus secciones del precio libre), Menús y combos y Suplementos listan las
   categorías para elegirlas, por el nombre en el idioma de quien mira y con su tipo vigente.
Entra: lo que ya está guardado en Reglas y Categorías.
Sale: lo que la línea de venta congela: categoría, tipo combinado, país, región y regla. Una línea con
categoría y sin regla se rechaza, nunca cae al 0 %: el TPV dice «… no se puede cobrar: ninguna regla
fiscal se aplica aquí a su categoría fiscal …» y la factura, «Ninguna regla fiscal se aplica hoy a la
categoría fiscal …» (TAX-F11). Qué hacer con una línea sin categoría es cosa de Ventas.
Si falla: el cajero no cobra con un tipo supuesto.
Implicados: COMBO-F09, INVENTORY-F01, INVENTORY-F02, INVOICE-F01, INVOICE-F03, MODIFIER-F07, SALE-F01,
SALE-F07, SERVICE-F01

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de la propia
persona) y la API, con las mismas reglas y los mismos permisos. Una llave de API del negocio llega a menos,
lo mismo que en el producto actual: ver las categorías, las reglas y los alias, leer un texto como
categoría, y poner fecha de fin a una regla o reactivarla. Pensado para la voz: una
categoría se nombra por su clave, por su nombre (en español o en inglés) o por un alias («Restauración
— comida», «comida», `restaurant.food`), y una regla por su id o por su país, región y categoría
(«la del IVA de la comida en España»: al desactivarla o ponerle fecha de fin, la vigente hoy; al
reactivarla, la última desactivada).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las categorías, con búsqueda, filtro de origen, páginas (hasta 100) y su tipo vigente hoy en un país y región | ver | F01, F19 | `tax.category.list` |
| Una categoría por su clave, con su nombre traducido | ver | F02, F19 | `tax.category.get` |
| Las reglas, con búsqueda, filtros (país, región, categoría, tipo, calificación, estado) y páginas | ver | F03 | `tax.rule.list` |
| Cuántas reglas raíz aplican hoy en el país del negocio y si los impuestos están configurados (el aviso y el paso «Tus impuestos» del Inicio) | ver | F17 | `tax.rule.status` |
| Las reglas raíz de las que puede colgar un componente en un país, región y categoría: las mismas que acepta el alta (también una raíz que empieza en el futuro; una sin impuesto, solo para un componente al 0 %) | ver | F06 | `tax.rule.parent_candidates` |
| Los países en los que el negocio tiene reglas (todas, activas o desactivadas), para el filtro País | ver | F03, F11 | `tax.rule.countries` |
| Los alias, con búsqueda, filtros (categoría, origen) y páginas | ver | F13, F15 | `tax.alias.list` |
| La categoría que corresponde a un texto de fuera, y por qué casó | ver | F15 | `tax.alias.resolve` |
| El impuesto de un importe: base, cuota, total, tipo, calificación y desglose | ver | F18, F19 | `tax.rate.calculate` |
| El país y el territorio fiscal del negocio, el impuesto de ese territorio (`tax_kind`: IVA, IGIC o IPSI) y los territorios que puede elegir | ver | F11 | `tax.settings.get` |

Categorías, reglas, alias, el estado de configuración, las raíces de un componente, los países y los ajustes se pueden seguir en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea una categoría fiscal propia | gestionar | F02, F15 | `tax.category.create` |
| Crea una regla (raíz o componente) | gestionar | F04, F05, F06, F11 | `tax.rule.create` |
| Crea hasta 100 reglas raíz, todas o ninguna | gestionar | F12 | `tax.rule.bulk_create` |
| Pone la fecha de fin de una regla | gestionar | F07 | `tax.rule.end` |
| Desactiva una regla | gestionar | F08 | `tax.rule.deactivate` |
| Reactiva una regla | gestionar | F08 | `tax.rule.activate` |
| Crea un alias aprendido | gestionar | F14, F15 | `tax.alias.create` |
| Guarda el territorio fiscal del negocio (o todo el país) | gestionar | F11 | `tax.settings.update` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Categoría nueva | Crear una categoría | Cuál (`id`, `key`) | `tax.category.created` |
| Regla nueva | Crear una regla (también por lote, una por regla) | Cuál, su país, región, categoría y % | `tax.rule.created` |
| Regla con fecha de fin | Poner la fecha de fin | Cuál y su fecha de fin | `tax.rule.ended` |
| Regla desactivada | Desactivar | Cuál | `tax.rule.deactivated` |
| Regla reactivada | Reactivar | Cuál | `tax.rule.activated` |
| Alias nuevo | Crear un alias | Cuál, su texto y su categoría | `tax.alias.created` |
| Territorio fiscal cambiado | Guardar otro territorio | El país y el territorio (vacío = todo el país) | `tax.settings.updated` |

Qué refresca cada aviso: las categorías, con «categoría nueva», con los cuatro de reglas y con
«territorio fiscal cambiado» (el tipo vigente sale en la tabla); las reglas y el estado de
configuración, con los cuatro de reglas y el del territorio; los ajustes, con «territorio fiscal
cambiado»; los alias, con «alias nuevo». En Ventas, la caja abierta y el tipo de las secciones se
recalculan con los cuatro de reglas y con el del territorio; en Facturación, el tipo general con que arranca
una línea de la factura manual, también.

### A qué reacciona y lo que necesita de otras apps
Nada: Impuestos no depende de ninguna app ni reacciona a avisos de otras.

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Inventario | Elegir la categoría fiscal de un producto o de una categoría, con su tipo; reconocer la columna fiscal de un CSV y, al importar, aprender un texto o crear la categoría que falta | `tax.category.list`, `tax.alias.resolve`, `tax.alias.create`, `tax.category.create` |
| Servicios | Elegir la categoría fiscal de un servicio y la de por defecto, con su tipo | `tax.category.list` |
| Ventas | El tipo y la calificación de cada línea al cobrar, con el cálculo de TAX-F18, y el tipo de cada sección, en el país y el territorio fiscal del negocio; elegir la categoría de una sección; el nombre del impuesto del territorio («IVA», «IGIC», «IPSI») | `tax.rate.calculate` (su función, dentro de su operación), `tax.category.list`, `tax.settings.get` |
| Facturación | El tipo y la calificación de cada línea con categoría; el impuesto de una línea sin regla, el de su territorio; el nombre del impuesto del territorio | `tax.rate.calculate` (su función, dentro de su operación), `tax.settings.get` |
| Menús y combos, Suplementos | Elegir la categoría fiscal propia de un menú o de una opción, con su tipo | `tax.category.list` |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver categorías, reglas, alias y el territorio fiscal, y calcular | sí | sí | sí | sí | `tax.view` |
| Crear categorías, reglas y alias; poner fecha de fin, desactivar y reactivar reglas; cambiar el territorio fiscal | sí | sí | sí | no | `tax.manage` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); el
cajero del producto actual es un empleado.

## Para quien lo mantiene

- Anatomía de servidor completa: `apps.py`, `models.py` (`TaxCategory`, `TaxRule`, `TaxAlias`, `TaxSettings`),
  `migrations/` (`0002` siembra el catálogo de fábrica, con reverso; `0005` añade `retail.alcohol` sin tocar lo
  que el hub ya tenga; `0006` crea `TaxSettings`), `schemas.py`, `queries.py`, `services.py`, `events.py`,
  `live.py`, `api.py`, `admin.py`, `locale/` y un `tests/test_<fichero>.py` por fichero, y las páginas
  (`frontend/`: Categorías, Reglas, Alias y Ajustes, con sus diálogos) con su Vitest y su e2e por flujo en
  tres tamaños (`tests/e2e/tax-flows.spec.ts`, más `tax-categories`, `tax-rules`, `tax-employee`,
  `tax-region-sale` y `tax-region-no-national-fallback`). País y Categoría de las altas son el `Combo` de
  `@erplora/ui` (el `ok-combo` de antes): la categoría se busca en el servidor (`tax.category.list` por
  nombre), nunca se carga entera.
- **Contrato con quien enlaza una categoría**: `TaxCategory` tiene clave UUIDv7 y `key` única (la
  `tax_category_key` enlazable). Ponen su FK aquí, todas `PROTECT`, Inventario (producto y categoría),
  Servicios (servicio y ajustes), Ventas (sección), Menús y combos (menú) y Suplementos (opción). Ninguna
  operación borra ni desactiva una categoría; desactivarla en el admin del Hub no es un borrado (no espera a
  ninguna escritura) y deja sin vender lo que la nombra hasta que se elija otra.
- **La lectura retenida de una categoría** (`queries.held_categories(keys)`, hub#62): `FOR KEY SHARE` en
  orden de clave, el mismo patrón que `held()` de Inventario. La usa Servicios al guardar un servicio, el
  alta en bloque o sus ajustes, para que un borrado a la vez espere a la escritura o la rechace como una
  clave que no existe (422 `service.tax_category_unknown`), nunca con un 500 en el COMMIT.
- **La resolución, una sola vez** (`queries.resolve_tax` y `queries.calculate_tax`): raíces activas y
  vigentes en la fecha, del país y la categoría; la región exacta gana a la del país entero y nunca se
  usa otra región; una región con impuesto propio (`own_tax_kind`: ES-CN, ES-CE, ES-ML) solo toma sus
  reglas, nunca las del país entero (`pick_root`, también en `current_rates`): sin la suya, `tax.no_rate`; dentro de un nivel, la de «Vigente desde» más reciente y, a igualdad, el `id` menor.
  Sus componentes (hijos activos y vigentes, por `id`) se suman sobre la misma base. La calificación y
  la familia del impuesto son siempre las de la raíz. Ventas y Facturación (que requieren Impuestos)
  llaman a esas funciones dentro de su propia operación.
- **Dinero**: céntimos enteros; `Decimal` exacto y redondeo a mitad hacia arriba (`ROUND_HALF_UP`).
  Los % se guardan con dos decimales. Con el impuesto incluido, el céntimo de ajuste va al último
  componente con tipo mayor que 0: uno al 0 % nunca lleva cuota.
- **País y región en cualquier caso**: `resolve_tax` y `calculate_tax` los pasan a mayúsculas, porque
  Ventas y Facturación los llaman sin pasar por los esquemas.
- **La jurisdicción del negocio, una sola fuente** (TAX-F11, pm#629 VF-17): `queries.business_jurisdiction()`
  da `(país, región)`: el país es `DEFAULT_COUNTRY` (`ES`) hasta que el Hub reciba el de la cuenta del SaaS
  (registro de la fase 2; el SaaS lo bloquea cuando el negocio está listo) y la región es la fila única
  `TaxSettings` (`tax_settings_single_row`; vacía = todo el país). `resolve_tax`, `calculate_tax`,
  `tax.rate.calculate` y `tax.category.list` la usan cuando no se nombra país; nombrar un país pide ese
  país solo, con la región que se diga. Una región de otro país que el que toca es 422 en `region_code`,
  nunca el tipo nacional en silencio. `tax.settings.update` solo admite los territorios con impuestos
  propios del país (`TAX_REGIONS`: ES-CN, ES-CE, ES-ML), 422 `tax.region_not_available`; su evento va en
  `RULE_EVENTS`, así que la caja y las listas vivas se recalculan. Ventas (`business_country`, el tipo de
  las secciones y `tax_closer`) y Facturación (`resolve_tax` de una línea con categoría) no pasan región
  suelta: leen esta fuente.
- **El impuesto de un territorio** (`REGION_TAX_KINDS`; `queries.tax_kind_of(país, región)` y
  `business_tax_kind()`): `igic` en ES-CN, `ipsi` en ES-CE y ES-ML, `vat` en el resto (una región de otro
  país, también). Lo llevan lo que no tiene regla de la que sacarlo: la línea de factura con tipo tecleado
  (el territorio del negocio hoy), la línea de venta sin su regla (`_charged_kind` de Facturación: el
  territorio que la línea congeló al cobrarse), el 0 % pedido expresamente (`fallback_zero`) y el alta de
  una regla sin `tax_type`. VeriFactu lo declara como `Impuesto` 03, 02 o 01.
- **El impuesto del territorio lo publica solo Impuestos** (ronda 2026-10-17 de PLAN-HUB): `tax.settings.get`
  (y la respuesta de `tax.settings.update`) lo devuelve en `tax_kind`, vivo sobre `tax.settings.updated`.
  Ninguna otra app lo republica con una operación propia (Ventas y Facturación tenían una fachada cada una;
  se borraron). En la SPA, `useTaxKind()` y `useTaxName()` de `frontend/composables/useTaxName.ts` lo leen
  con una sola suscripción por pestaña y dan la familia y su nombre corto («IVA», «IGIC», «IPSI»,
  `tax.common.taxName.*`); `taxNameKey(familia)` nombra cualquier otra (la que declararon las ventas de un
  periodo). En el servidor, `schemas.TAX_KIND_NAMES` da el mismo nombre corto a un mensaje («Falta configurar
  su IGIC.», el 409 `sale.tax_category_missing` de Ventas). Todo rol que vende o factura tiene `tax.view`.
- **Solape**: crear, reactivar, poner fecha de fin y el lote bloquean la fila de la categoría
  (`select_for_update`) antes de comprobar; dos escrituras a la vez sobre la misma categoría se ponen
  en cola y la segunda ve la primera (tests con dos sesiones reales para crear, reactivar, poner fecha
  de fin y el lote). Las fechas son inclusivas; vacías = abiertas.
- **Clave natural de la raíz** (`tax_rule_root_natural_key`, la `ix_tax_rule_root_natural` del producto
  actual): una raíz por país, región, categoría y primer día, también las desactivadas; un primer día
  vacío es «desde siempre», así que dos vacías son la misma. Las operaciones la comprueban antes y
  responden 409 `tax.rule_exists`; si la gemela está activa, el rechazo es el del solape.
- **Reactivar por país, región y categoría** trae la desactivada más recientemente (`updated_at`).
- **Comprobaciones también en la base de datos**: % entre 0 y 100, 0 % en las clases que no cobran
  impuesto y rango de fechas hacia delante (`CheckConstraint`).
- Los nombres de las categorías de fábrica se traducen en el código (`SYSTEM_CATEGORY_LABELS`, con su
  `es` en `locale/`), no en la base de datos: en la fila queda el nombre en inglés.
- **Administrador de Django con CRUD completo** (ronda 12, PLAN §17), solo en `hubs.erplora.com` y
  para el staff de la plataforma. Lo que guarda de categorías, reglas y alias no pasa por las operaciones:
  no deja aviso ni comprueba el solape ni la coherencia de un componente; la base de datos sigue rechazando
  el % fuera de 0–100, el % en una clase sin impuesto, el rango al revés y la raíz gemela. Los ajustes del
  negocio sí (hub#42): el territorio es un desplegable con los del país del negocio más «Todo el país», se
  guarda por `tax.settings.update` (su actor y su evento en el outbox) y no se añade una segunda fila ni se
  borra la que hay (borrarla movería el negocio a todo el país en silencio).
- **Paridad con el producto actual**: las listas aceptan los mismos filtros, búsqueda y orden
  (`sort`, `dir`) que sus tablas; las filas llevan las mismas columnas (también Activa, siempre «Sí»:
  como antes, ninguna operación archiva una categoría o un alias). El alta de alias acepta Origen y la
  de categoría, `is_system` (solo por la API), como antes. `expose_api` es el del manifiesto viejo:
  `tax.category.list`/`get`, `tax.rule.list`, `tax.alias.list`/`resolve`, `tax.rule.end` y
  `tax.rule.activate`.
- **Asistente**: cada operación declara `ai` (descripción; en las escrituras, `risk`: `high` en las de
  reglas, que deciden lo que se cobra y se declara, y en el lote) y cada campo de `schemas.py` su
  `description` (el JSON Schema de la herramienta). La tarjeta de confirmación nombra cada dato por el
  `verbose_name` del modelo; el que ningún modelo nombra (`tax_category_key`) lleva un `title` en inglés con
  `gettext_noop` y su español en el catálogo de Impuestos, la palabra de las pantallas («Categoría»). Lo
  vigila `tests/test_integration_assistant.py`, que recorre todas las escrituras `tax.*` del registro.
- **País y región** salen de `pycountry` (ISO 3166-1 y 3166-2), no de una lista copiada.
- **Decisión de mercado: «Tus impuestos» (TAX-F17) en las pantallas de Impuestos**: el mercado avisa de
  los tipos que faltan en una lista de primeros pasos del inicio (Square, Odoo, Lightspeed, Business
  Central) y en la propia pantalla de impuestos (WooCommerce, Shopify, Toast). El aviso va en Categorías,
  Reglas y Alias y lee `tax.rule.status` sin país; el paso «Tus impuestos» de la lista «Termina de
  configurar tu negocio» del Inicio (ronda 2026-10-21 de `PLAN-HUB.md`, que trae esa lista a `base`)
  lee la misma consulta y dice las mismas palabras (FIX-TAX-SETUP-HOOKS).
- **El paso del Inicio** (PLAN-HUB ronda 2026-10-21; FIX-TAX-SETUP-HOOKS): `TaxConfig.setup` declara el `setup` del
  módulo viejo (`module.json`, taxes#19): clave `tax.rules`, sobre `tax.rule.status` sin país, hecho con
  `configured` (el mismo campo que lee el aviso; el viejo miraba `matching_rules`, que es lo mismo), orden 20,
  `required` (nivel «Importante»), permiso `tax.manage`, ruta `/tax/rules` y `refresh_on`
  `events.RULE_IN_FORCE_EVENTS` (regla creada, una o varias; terminada; desactivada; reactivada). El cambio de
  territorio (`tax.settings.updated`) no entra: el paso cuenta reglas de cualquier país y región. Una regla con
  fecha de inicio futura que empieza a regir no emite evento: el Inicio la ve al volver a abrirse, como el aviso.
  El título y la descripción son los del aviso (el viejo decía `Set the VAT rates for the country you sell in,
  so the till can price a sale.`), con su español en `locale/`. Sin paneles ni campana: el módulo viejo no los
  declaraba. Pruebas: `tests/test_apps.py` y `tests/test_integration_home.py` (con `base` real y dos hubs).
- **Decisión de mercado: el territorio fiscal del negocio (TAX-F11)**: vive en Impuestos, en la pestaña
  **Ajustes**, como el «país fiscal» de Odoo en los ajustes de Contabilidad y el régimen IGIC de Holded o Sage
  en los de impuestos; Square, Shopify y Toast lo sacan de la dirección del local. El país no se edita aquí:
  es el de la cuenta del SaaS, que lo bloquea cuando el negocio está listo, y llega al Hub con su registro
  (fase 2); hasta entonces, España. Ventas y Facturación leen los dos de la misma fuente (pm#629, VF-17).

## Lo que queda fuera

- **Que «Tus impuestos» mire el país y el territorio del negocio**: `SetupNotice.vue` y el paso del Inicio
  piden `tax.rule.status` sin país, así que cuenta las reglas raíz de cualquier país y territorio; un negocio de
  Canarias, Ceuta o Melilla con solo las reglas de fábrica (IVA) no ve el aviso, aunque el TPV no le deja
  cobrar esas categorías y le dice por qué. Es comportamiento nuevo: aplazado de la migración (ronda
  FIX-TAX-REGION-NATIONAL-FALLBACK de `PLAN-HUB.md`).
- **El país del negocio**: es `DEFAULT_COUNTRY` (`ES`) hasta que el Hub reciba el de la cuenta del SaaS con
  el registro de la fase 2 (`PUT /internal/hubs/{id}` → `control.Hub`); no se edita en el Hub (BASE-G97
  sigue `no hecho` por eso).
- **«Hoy» en la zona del negocio**: en la fase 1 es el de Madrid (`settings.TIME_ZONE`), también en
  Canarias, donde un cambio de tipo empieza una hora antes de su medianoche (la zona horaria del negocio en
  dos fuentes es una contradicción señalada en la ronda CLOSE-SCHEDULE de `PLAN-HUB.md`).
- **Tipos de fábrica de IGIC, IPSI, recargo de equivalencia o de otros países**: no se siembran, a propósito
  (un tipo inventado se declararía); los crea el negocio (TAX-F04, TAX-F06, TAX-F11).
- **`useServerTable`/`useLiveList` y `formatPercent`/`formatDate` en `@erplora/ui`**: siguen en
  [`UI-REQUESTS.md`](UI-REQUESTS.md), sin llegar a `ui`; propuestos para `## 6` de `MIGRATION.md` como
  `tax:ui-live-server-table` y `tax:ui-percent-date-format`.

## Lo que NO hace, a propósito

- No fija el precio ni decide si va con el impuesto incluido: eso es de Ventas.
- No cierra el tique ni agrupa por tipo para la factura o el registro de la AEAT: eso es de Ventas y
  Facturación.
- No guarda el país del negocio: es el de su cuenta de ERPlora. Sí guarda su territorio fiscal (TAX-F11).
- No edita una regla (se cambia con fecha de fin y una regla nueva) ni borra reglas, categorías o
  alias; no renombra ni archiva una categoría o un alias.
- No hace depender el recargo de equivalencia del cliente: se suma a toda venta de la categoría.
- No traduce los códigos de exención ni de régimen ni habla con la AEAT.
- No siembra tipos de IGIC, IPSI, recargo de equivalencia ni de otros países.

## Cambios frente al producto actual

1. **Ninguna regla incoherente ni solapada puede nacer**, tampoco por el lote, que ahora aplica las
   mismas comprobaciones que el alta y es todo o nada. Por eso se retiran TAX-F09 (reparar) y TAX-F10
   (marcar solapes) y sus marcas `is_incoherent` y `overlaps`: eran salidas para filas guardadas antes
   de las guardas, y aquí no las hay.
2. **Los rechazos dicen el campo**: rango de fechas al revés, % en una clase sin impuesto, región de
   otro país, categoría inexistente (422 por campo); clave o alias repetidos (409 con su campo).
3. **Desactivar** una regla que no existe da 404 y una ya desactivada, 409 (antes respondía bien sin
   hacer nada); reactivar una ya activa, 409.
4. **El alias se guarda normalizado** (minúsculas, espacios juntos) en toda puerta: antes la pantalla
   guardaba mayúsculas que nunca casaban.
5. **Una categoría se nombra también por su nombre o un alias** (alta de regla y de alias, cálculo,
   consulta) y **una regla por su país, región y categoría** (fecha de fin, desactivar, reactivar),
   además de por su clave o su id: el asistente se usa por voz.
6. **La región se comprueba contra la lista ISO 3166-2** (`pycountry`), no solo por su forma: una región
   que no existe nunca casaría.
7. **La fecha por defecto del cálculo es la del negocio**, no la UTC (en la fase 1, la de Madrid).
8. **Un componente sale debajo de su raíz** en la lista de reglas.
9. **El cajero** es un empleado: recibe `tax.view` (ver y calcular).
10. **`restaurant.alcohol` se siembra al 10 %** (antes, 21 %): las bebidas alcohólicas servidas para
   consumir en el local son un servicio de hostelería (art. 91.Uno.2.2º de la Ley 37/1992). El alcohol
   para llevar o a domicilio, al 21 %, tiene su categoría: `retail.alcohol`. Un hub que ya tuviera la
   semilla anterior recibe `retail.alcohol` (migración 0005) y conserva su regla de
   `restaurant.alcohol`: una migración nunca reescribe un tipo; se cambia con TAX-F07.
11. **«Tus impuestos» sale también en las pantallas de Impuestos** (TAX-F17). En el producto actual era solo un
   paso de la lista de primeros pasos del inicio (hub#2356); el paso sigue en «Termina de configurar tu negocio»
   del Inicio, con las mismas palabras que el aviso de Categorías, Reglas y Alias.
12. **El territorio fiscal se elige en una pantalla** (Impuestos → Ajustes, TAX-F11): antes solo se fijaba
   por la API de ajustes, y Ajustes del Hub dejaba elegir el país (España o Portugal), que ahora es el de
   la cuenta de ERPlora. Solo se admiten los territorios con impuestos propios (Canarias, Ceuta, Melilla),
   nunca un código cualquiera (hub#1496).
