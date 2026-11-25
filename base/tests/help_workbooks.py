"""Made-up WORKBOOKs of the Tables module for the tests of its help window: Spanish (the source), English, and a third
language whose words no catalogue of the Hub knows, so that nothing in the reading can assume a pair of languages.

Each one has the same shape: what the module is for (a paragraph wrapped over two lines and a code block with headings
inside, then who uses it and what it does not do under their ``###``, with a list whose items go on over indented
lines), the screens heading with three tabs (one with a window, ``####``), a section that names no tab,
and flows that are done on a tab, done through a window, not done, and done on no tab; some statuses carry a note after
a dash, a colon or a parenthesis, a window's title has its own parentheses, and some paragraphs are wrapped over lines.
"""

from pathlib import Path
from types import SimpleNamespace

from django.apps import apps
from live.meta import Help

from base import catalog
from base.queries import app_help
from base.workbook_help import Tab, Words
from base.workbook_sections import marked

ES = """\
# Mesas
Prefijo: TABLE

## Para qué sirve y para quién

Mesas es el **plano de la sala**: sus zonas
y sus mesas.

```
## Esto no es un encabezado
### Ni esto
```

### Quién la usa

- El **responsable** dibuja el plano y cambia
  el aforo de cada mesa.
- El **empleado** sienta a la gente.

### Lo que no hace

No cobra.

## Pantallas

El menú **Mesas** tiene cuatro pestañas.

### Plano de sala
Tocar una mesa abre su ventana:

- libre: pregunta los comensales
  y la sienta.
  - con reserva: dice a nombre de quién.

#### Cobrar mesa (cuenta)
Pide el importe y cobra.

### Zonas
Una tabla con el nombre y el color
de cada zona.

### Ajustes
Los avisos de tiempo.

### Pantalla retirada
Ninguna pestaña se llama así.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| TABLE-F01 | Crear una zona | hecho |

### TABLE-F01 Crear una zona
Estado: hecho — en la tableta y en el móvil
Actor: responsable
Pantalla: Zonas
Pasos:
1. En **Mesas → Zonas** pulsa «+» y escribe el nombre, que después
   sale como pestaña del plano.
2. Pulsa «Añadir zona».
Entra: el nombre y el color.
Sale: la zona (avisa: `table.zone.created`).
Si falla: sin nombre, el botón no se activa. Un nombre repetido dice
«Ya hay una zona con ese nombre.».
Implicados: TABLE-F02

### TABLE-F02 Cobrar una mesa desde el plano
Estado: hecho (también desde el TPV)
Vertical: restaurante
Actor: empleado
Pantalla: Plano de sala (Servicio, «Mesa N»); asistente
Pasos:
1. Toca la mesa ocupada.
2. Pulsa «Cobrar».
Por el asistente: «cobra la mesa 4».
Implicados: TABLE-F01

### TABLE-F03 Cobrar desde la ventana de cobro
Estado: hecho: también por la API
Actor: empleado
Pantalla: Cobrar mesa, Zonas
Pasos:
1. Escribe el importe.
Si falla: «No se pudo cobrar».

### TABLE-F04 Juntar dos zonas
Estado: no hecho — falta la pantalla
Actor: responsable
Pantalla: Zonas
Pasos:
1. Aún no se puede.

### TABLE-F05 Olvidar a un cliente borrado
Estado: hecho
Actor: el sistema
Pantalla: ninguna (se ve en el Plano de sala)
Pasos:
1. Cambia el nombre por «Cliente borrado».

## Para quien lo mantiene

### TABLE-F06 Lo que solo lee quien lo mantiene
Estado: hecho
Pantalla: Zonas
Pasos:
1. Nada de esto se publica.
"""

EN = """\
## What it is for and who it is for

Tables is the **floor plan of the room**: its zones
and its tables.

```
## This is no heading
### Nor is this
```

### Who uses it

- The **manager** draws the plan and changes
  the capacity of each table.
- The **employee** seats people.

### What it does not do

It does not charge.

## Screens

The **Tables** menu has four tabs.

### Floor plan
Tapping a table opens its window:

- free: asks for the guests
  and seats them.
  - with a booking: says whose it is.

#### Charge table (check)
Asks for the amount and charges it.

### Zones
A table with the name and the colour of each zone.

### Settings
The time warnings.

### Retired screen
No tab has this name.

## Flows

### TABLE-F01 Create a zone
Status: done — on the tablet and on the phone
Actor: manager
Screen: Zones
Steps:
1. In **Tables → Zones** tap «+» and write the name, which then
   shows as a tab of the plan.
2. Tap «Add zone».
In: the name and the colour.
Out: the zone (notifies: `table.zone.created`).
If it fails: without a name, the button stays off. A repeated name says
"There is already a zone with that name.".
Involved: TABLE-F02

### TABLE-F02 Charge a table from the plan
Status: done (also from the POS)
Vertical: restaurant
Actor: employee
Screen: Floor plan (Service, «Table N»); assistant
Steps:
1. Tap the occupied table.
2. Tap «Charge».
Through the assistant: «charge table 4».
Involved: TABLE-F01

### TABLE-F03 Charge from the charge window
Status: done: also through the API
Actor: employee
Screen: Charge table, Zones
Steps:
1. Write the amount.
If it fails: «Could not charge».

### TABLE-F04 Join two zones
Status: not done — the screen is missing
Actor: manager
Screen: Zones
Steps:
1. Not possible yet.

### TABLE-F05 Forget an erased customer
Status: done
Actor: the system
Screen: none (it is seen on the Floor plan)
Steps:
1. Changes the name to «Erased customer».
"""

#: A language no catalogue of the Hub has: its words come from nowhere but this file and ``EO_WORDS``.
EO = """\
## Por kio ĝi servas

Tabloj estas la **plano de la salono**.

## Ekranoj

### Salonplano
Tuŝi tablon malfermas ĝian fenestron.

#### Pagi tablon (konto)
Petas la sumon.

### Zonoj
Tabelo de la zonoj.

## Fluoj

### TABLE-F01 Krei zonon
Stato: farita — en la tabulkomputilo kaj en la telefono
Ekrano: Zonoj
Paŝoj:
1. Tuŝu «+» kaj skribu la nomon, kiu poste
   aperas en la plano.
Se ĝi malsukcesas: sen nomo, la butono restas
malŝaltita.

### TABLE-F02 Pagi tablon
Stato: farita
Ekrano: Pagi tablon
Paŝoj:
1. Tuŝu la tablon.

### TABLE-F04 Kunigi du zonojn
Stato: ne farita — mankas la ekrano
Ekrano: Zonoj
Paŝoj:
1. Ankoraŭ ne.
"""

ES_WORDS = Words(
    screens="Pantallas",
    done="hecho",
    keys={
        "status": "Estado",
        "vertical": "Vertical",
        "actor": "Actor",
        "screen": "Pantalla",
        "operations": "Operaciones",
        "steps": "Pasos",
        "in": "Entra",
        "out": "Sale",
        "failure": "Si falla",
        "assistant": "Por el asistente",
        "involved": "Implicados",
    },
)
EN_WORDS = Words(
    screens="Screens",
    done="done",
    keys={
        "status": "Status",
        "vertical": "Vertical",
        "actor": "Actor",
        "screen": "Screen",
        "operations": "Operations",
        "steps": "Steps",
        "in": "In",
        "out": "Out",
        "failure": "If it fails",
        "assistant": "Through the assistant",
        "involved": "Involved",
    },
)
EO_WORDS = Words(
    screens="Ekranoj",
    done="farita",
    keys={
        "status": "Stato",
        "vertical": "Vertikalo",
        "actor": "Aktoro",
        "screen": "Ekrano",
        "operations": "Operacioj",
        "steps": "Paŝoj",
        "in": "Eniras",
        "out": "Eliras",
        "failure": "Se ĝi malsukcesas",
        "assistant": "Per la asistanto",
        "involved": "Implikitaj",
    },
)


#: The made-up WORKBOOK of the Hub's own screens: three of its screens, a section that is no screen (the bell) and the
#: tasks done on them: anyone's, those of some roles, the system's, one on a screen for everyone and on one that is not,
#: and one that is not done.
PLATFORM_ES = """\
# Base
Prefijo: BASE

## Para qué sirve y para quién

Lo que el Hub trae **siempre**,
sin activar nada.

### De un vistazo

El `Inicio` (hub#1).

## Pantallas

### Inicio · Resumen
El negocio de un vistazo.

#### De arriba abajo
Los paneles (BASE-F02).

### La campana
Los avisos, en cualquier pantalla.

### Archivos
Los documentos del negocio.

### Sistema · Registros
Lo que ha pasado.

## Flujos

### BASE-F01 Ver el negocio de un vistazo
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
1. Entra en el Inicio.
Implicados: BASE-F02

### BASE-F02 Configurar lo que falta
Estado: hecho
Actor: propietario, administrador, responsable (el de guardia)
Pantalla: Inicio · Resumen
Pasos:
1. Pulsa «Configurar».

### BASE-F03 Empezar con una plantilla
Estado: hecho
Actor: propietario, administrador, personal de soporte
Pantalla: Inicio · Resumen
Pasos:
1. Elige la plantilla.

### BASE-F04 Vaciar el negocio
Estado: hecho
Actor: propietario
Pantalla: Inicio · Resumen
Pasos:
1. Escribe el nombre del negocio.

### BASE-F05 Mantener los paneles al día
Estado: hecho
Actor: sistema
Pantalla: Inicio · Resumen
Pasos:
1. El panel cambia solo.

### BASE-F06 Descargar un archivo
Estado: hecho
Actor: cualquier persona del negocio
Pantalla: Sistema · Registros, Archivos
Pasos:
1. Pulsa «Descargar».
Si falla: lo dice un aviso.

### BASE-F07 Ver las cuentas de la gestoría
Estado: parcial — falta la pantalla
Actor: gestoría
Pantalla: Archivos
Pasos:
1. Aún no se puede.

### BASE-F08 Ver los archivos
Estado: hecho
Actor: empleado, gestoría
Pantalla: Archivos
Pasos:
1. Abre la carpeta.

## Para quien lo mantiene

Nada.
"""
PLATFORM_EN = """\
## What it is for and who it is for

What the Hub **always** brings, with nothing to turn on.

### At a glance

The `Home` (hub#1).

## Screens

### Home · Summary
The business at a glance.

#### From top to bottom
The panels (BASE-F02).

### The bell
The notices, on any screen.

### Files
The business's documents.

### System · Logs
What has happened.

## Flows

### BASE-F01 See the business at a glance
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
1. Go to the Home.
Involved: BASE-F02

### BASE-F02 Set up what is missing
Status: done
Actor: owner, administrator, manager (the one on duty)
Screen: Home · Summary
Steps:
1. Tap "Set up".

### BASE-F03 Start with a template
Status: done
Actor: owner, administrator, support staff
Screen: Home · Summary
Steps:
1. Choose the template.

### BASE-F04 Empty the business
Status: done
Actor: owner
Screen: Home · Summary
Steps:
1. Write the business's name.

### BASE-F05 Keep the panels up to date
Status: done
Actor: system
Screen: Home · Summary
Steps:
1. The panel changes by itself.

### BASE-F06 Download a file
Status: done
Actor: anyone of the business
Screen: System · Logs, Files
Steps:
1. Tap "Download".
If it fails: a notice says so.

### BASE-F07 See the accountancy firm's accounts
Status: partial — the screen is missing
Actor: accountancy firm
Screen: Files
Steps:
1. Not possible yet.

### BASE-F08 See the files
Status: done
Actor: employee, accountancy firm
Screen: Files
Steps:
1. Open the folder.
"""


def tabs(*labels: str) -> tuple[Tab, ...]:
    """The four tabs of Tables (floor plan, zones, tables, settings) labelled in one language."""
    ids = ("floor_plan", "zones", "tables", "settings")
    paths = ("/table/floor-plan", "/table/zones", "/table/tables", "/table/settings")
    return tuple(Tab(id_, label, path) for id_, label, path in zip(ids, labels, paths, strict=True))


ES_TABS = tabs("Plano de sala", "Zonas", "Mesas", "Ajustes")
EN_TABS = tabs("Floor plan", "Zones", "Tables", "Settings")
EO_TABS = tabs("Salonplano", "Zonoj", "Tabloj", "Agordoj")


def ready_platform(monkeypatch, root: Path) -> SimpleNamespace:
    """The only app with its help ready: the Hub's own screens, its WORKBOOKs the made-up ones written in ``root``."""
    write_workbooks(root, {"en": PLATFORM_EN}, source=PLATFORM_ES)
    base = apps.get_app_config("base")
    platform = SimpleNamespace(
        label=base.label, kind=base.kind, verbose_name=base.verbose_name, path=str(root), help=Help()
    )
    _only_ready(monkeypatch, platform)
    return platform


def _only_ready(monkeypatch, app: SimpleNamespace) -> None:
    monkeypatch.setattr(app_help, "all_live_app_configs", lambda: [app])
    # A cache of its own, so that no help read by another test (of another folder) answers for this one.
    monkeypatch.setattr(app_help, "_READ", {})


def write_workbooks(root: Path, translations: dict[str, str], source: str = ES) -> Path:
    """``WORKBOOK.md`` in ``root`` and, for each language, its ``WORKBOOK.<language>.md`` current with it."""
    (root / "WORKBOOK.md").write_text(source, encoding="utf-8")
    for language, body in translations.items():
        text = marked(catalog.user_part(source), body)
        assert text is not None, f"the made-up {language} has other headings than its source"
        (root / f"WORKBOOK.{language}.md").write_text(text, encoding="utf-8")
    return root


def ready_tables(monkeypatch, root: Path, ready: Help | None = None) -> SimpleNamespace:
    """The only module with its help ready: Tables' name and menu, its WORKBOOKs the made-up ones written in ``root``
    (Spanish and a current English). A stand-in, not Tables itself: Django reads each app's catalogue from the app's
    folder, so moving the real one's folder to ``root`` would leave its labels untranslated."""
    table = apps.get_app_config("table")
    module = SimpleNamespace(
        label=table.label,
        kind=table.kind,
        verbose_name=table.verbose_name,
        navigation=table.navigation,
        path=str(write_workbooks(root, {"en": EN})),
        help=ready or Help(),
    )
    _only_ready(monkeypatch, module)
    return module
