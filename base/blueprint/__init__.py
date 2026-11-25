"""Blueprints: the ``.blueprint.zip``, the catalogue of seeds by vertical and what travels of each app, behind
Settings › Data and the Home's card.

A blueprint is a manifest (who made it, for what, its language and country, the apps it turns on) and, per dataset,
the rows that travel. A **dataset** is one kind of thing an app lets travel (inventory's categories, its products,
the tables of the room…): it reads its rows with that app's own list and writes them with that app's own create, so
the app's rules hold for an import too, and never a table is dumped. Rows name each other by their natural
key — a product's categories by name, a table's zone by name — never by an id of the business that made the file.
People, PINs and fiscal data have no dataset: they never travel, and a file that brings them has them dropped on
reading (``Bundle.dropped``).

- The file (``archive``): ``manifest.json``, ``data/<dataset>.json`` and the rows' own photos at ``media/<name>`` in
  a zip (:func:`archive.read_zip`, :func:`archive.write_zip`), read with limits (20 MB, 100 MB inflated, 1 000
  entries) and refused with a reason the person can read (:class:`archive.BlueprintInvalid`).
- Images (``photos``, with ``base.images``): an image of the shared library travels as its reference
  (``catalog:<folder>/<name>``), a photo of a row's own inside the file (:func:`photos.export_media`); loading it
  copies the photo under a new name through the app's own upload, and a row whose image cannot be set loads without
  it and is told (:func:`photos._load_image`).
- The catalogue (``seeds``): the seeds of ``base/seeds/<vertical>.<language>.json``, one per vertical and language;
  what a seed turns on is its vertical's apps (``base.catalog.verticals.template_apps``), what it brings is its own data.
- :func:`loading.apply` loads a blueprint app by app, each part on its own: a row an app refuses fails alone and is
  told, the rest loads, and loading again duplicates nothing (each dataset skips what is already there). Personal
  data (the customers) travels only in a backup, never in a template. Before it, ``base.blueprint.import`` turns on
  the apps the manifest lists that are off (a hub is born with every app off); one it could not turn on (the plan's
  limit, no right to it) loads nothing and its report says why. A load kept, and the part of it that waits for an
  app being set up, is ``loads``'s.
- :func:`removal.undo` removes exactly the rows a load created; :func:`removal.reset` every row of the apps chosen;
  both through the apps' own delete (or archive).

No ORM here: every read and write is an operation of its app, called as the person who asked
(``live.operations.get``), so its permission, its transaction and its events are the operation's own.
"""

from . import (
    archive as archive,
    calls as calls,
    datasets as datasets,
    export as export,
    loading as loading,
    loads as loads,
    photos as photos,
    preview as preview,
    removal as removal,
    seeds as seeds,
)
