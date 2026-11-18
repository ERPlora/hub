"""Made-up WORKBOOKs of the Tables module for the tests of its help window: Spanish (the source), English, and a third
language whose words no catalogue of the Hub knows, so that nothing in the reading can assume a pair of languages.

Each one has the same shape: what the module is for (with a list whose items go on over indented lines, and a heading
inside a code block), the screens heading with three tabs (one with a window, ``####``), a section that names no tab,
and flows that are done on a tab, done through a window, not done, and done on no tab.
"""

from pathlib import Path
from types import SimpleNamespace

from django.apps import apps
from live.meta import Help

from base import catalog
from base.queries import app_help
from base.workbook_help import Tab, Words

ES = """\
# Mesas
Prefijo: TABLE

## Para qué sirve y para quién

Mesas es el **plano de la sala**: sus zonas y sus mesas.

Quién la usa:

- El **responsable** dibuja el plano y cambia
  el aforo de cada mesa.
- El **empleado** sienta a la gente.

```
## Esto no es un encabezado
```

## Pantallas

El menú **Mesas** tiene cuatro pestañas.

### Plano de sala
Tocar una mesa abre su ventana:

- libre: pregunta los comensales
  y la sienta.
  - con reserva: dice a nombre de quién.

#### Cobrar mesa
Pide el importe y cobra.

### Zonas
Una tabla con el nombre y el color de cada zona.

### Ajustes
Los avisos de tiempo.

### Pantalla retirada
Ninguna pestaña se llama así.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| TABLE-F01 | Crear una zona | hecho |

### TABLE-F01 Crear una zona
Estado: hecho
Actor: responsable
Pantalla: Zonas
Pasos:
1. En **Mesas → Zonas** pulsa «+» y escribe el nombre, que después
   sale como pestaña del plano.
2. Pulsa «Añadir zona».
Entra: el nombre y el color.
Sale: la zona (avisa: `table.zone.created`).
Si falla: sin nombre, el botón no se activa.
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
Estado: hecho
Actor: empleado
Pantalla: Cobrar mesa, Zonas
Pasos:
1. Escribe el importe.
Si falla: «No se pudo cobrar».

### TABLE-F04 Juntar dos zonas
Estado: no hecho
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

Tables is the **floor plan of the room**: its zones and its tables.

Who uses it:

- The **manager** draws the plan and changes
  the capacity of each table.
- The **employee** seats people.

```
## This is no heading
```

## Screens

The **Tables** menu has four tabs.

### Floor plan
Tapping a table opens its window:

- free: asks for the guests
  and seats them.
  - with a booking: says whose it is.

#### Charge table
Asks for the amount and charges it.

### Zones
A table with the name and the colour of each zone.

### Settings
The time warnings.

### Retired screen
No tab has this name.

## Flows

### TABLE-F01 Create a zone
Status: done
Actor: manager
Screen: Zones
Steps:
1. In **Tables → Zones** tap «+» and write the name, which then
   shows as a tab of the plan.
2. Tap «Add zone».
In: the name and the colour.
Out: the zone (notifies: `table.zone.created`).
If it fails: without a name, the button stays off.
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
Status: done
Actor: employee
Screen: Charge table, Zones
Steps:
1. Write the amount.
If it fails: «Could not charge».

### TABLE-F04 Join two zones
Status: not done
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

#### Pagi tablon
Petas la sumon.

### Zonoj
Tabelo de la zonoj.

## Fluoj

### TABLE-F01 Krei zonon
Stato: farita
Ekrano: Zonoj
Paŝoj:
1. Tuŝu «+» kaj skribu la nomon, kiu poste
   aperas en la plano.
Se ĝi malsukcesas: sen nomo, la butono restas malŝaltita.

### TABLE-F02 Pagi tablon
Stato: farita
Ekrano: Pagi tablon
Paŝoj:
1. Tuŝu la tablon.

### TABLE-F04 Kunigi du zonojn
Stato: ne farita
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
        "steps": "Paŝoj",
        "in": "Eniras",
        "out": "Eliras",
        "failure": "Se ĝi malsukcesas",
        "assistant": "Per la asistanto",
        "involved": "Implikitaj",
    },
)


def tabs(*labels: str) -> tuple[Tab, ...]:
    """The four tabs of Tables (floor plan, zones, tables, settings) labelled in one language."""
    ids = ("floor_plan", "zones", "tables", "settings")
    paths = ("/table/floor-plan", "/table/zones", "/table/tables", "/table/settings")
    return tuple(Tab(id_, label, path) for id_, label, path in zip(ids, labels, paths, strict=True))


ES_TABS = tabs("Plano de sala", "Zonas", "Mesas", "Ajustes")
EN_TABS = tabs("Floor plan", "Zones", "Tables", "Settings")
EO_TABS = tabs("Salonplano", "Zonoj", "Tabloj", "Agordoj")


def header_of(source: str = ES) -> str:
    """The first line that makes a translation current with the customer's part of ``source``."""
    return catalog.en_header(catalog.source_hash(catalog.user_part(source)))


def write_workbooks(root: Path, translations: dict[str, str], source: str = ES) -> Path:
    """``WORKBOOK.md`` in ``root`` and, for each language, its ``WORKBOOK.<language>.md`` current with it."""
    (root / "WORKBOOK.md").write_text(source, encoding="utf-8")
    for language, body in translations.items():
        (root / f"WORKBOOK.{language}.md").write_text(f"{header_of(source)}\n\n{body}", encoding="utf-8")
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
    monkeypatch.setattr(app_help, "module_configs", lambda: [module])
    return module
