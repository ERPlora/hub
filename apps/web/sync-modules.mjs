// Copia los artefactos de los módulos instalados (module.json + dist/<id>.esm.js) a
// public/modules/** para que el shell pueda cargarlos en runtime con import() dinámico
// (Vite sirve public/ en la raíz, en dev y en build).
//
// En producción esto NO existe: el runtime (crates/server) sirve los módulos descargados
// del marketplace. Aquí es solo el puente para el shell web de desarrollo. ARQUITECTURA.md §4.
import { mkdirSync, copyFileSync, existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
// Source-of-truth de los módulos: el workspace de dev del toolkit en el ROOT del monorepo
// (ERPlora/modules-workspace/modules/<id>/, cada uno su propio repo git, creado/gestionado por
// @erplora/module-toolkit). hub/modules/ se reserva para los módulos INSTALADOS en runtime.
const MODULES_SRC = join(HERE, '../../../modules-workspace/modules');
const PUBLIC_DST = join(HERE, 'public/modules');

// Lote POS (Stencil→Lit, 2026-06-07): los módulos que el shell de desarrollo carga en runtime.
// En prod esto no existe (el runtime sirve los módulos del marketplace) — aquí es el puente del dev.
const MODULES = [
  'appointments', 'cart_checkout', 'cash_register', 'customers', 'inventory',
  'invoice', 'invoice_series', 'kitchen', 'online_booking',
  'orders', 'payment_gateways', 'payments', 'pricing', 'reservations',
  'sales', 'schedules', 'services', 'staff', 'tables',
  'tasks', 'taxes', 'tickets', 'verifactu', 'whatsapp_inbox',
];

for (const id of MODULES) {
  const src = join(MODULES_SRC, id);
  const manifestPath = join(src, 'module.json');
  if (!existsSync(manifestPath)) {
    console.warn(`! módulo ${id}: falta module.json (¿lo compilaste con module-cli build?)`);
    continue;
  }
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const entry = manifest.ui?.entry; // p. ej. dist/inventory.esm.js
  const bundlePath = join(src, entry ?? '');
  if (!entry || !existsSync(bundlePath)) {
    console.warn(`! módulo ${id}: falta el bundle ${entry}. Ejecuta: pnpm -F @erplora/module-cli build:inventory`);
    continue;
  }

  const dstDir = join(PUBLIC_DST, id);
  mkdirSync(join(dstDir, dirname(entry)), { recursive: true });
  copyFileSync(manifestPath, join(dstDir, 'module.json'));
  copyFileSync(bundlePath, join(dstDir, entry));

  // Sidecar de iconos (ADR-0036): SVG horneados del módulo, junto al bundle en dist/. El shell
  // (module-loader.loadMenu) lo lee para pintar los iconos de nav del módulo. Opcional.
  let iconsNote = '';
  const iconsPath = join(src, dirname(entry), 'icons.json');
  if (existsSync(iconsPath)) {
    copyFileSync(iconsPath, join(dstDir, dirname(entry), 'icons.json'));
    iconsNote = ' + icons.json';
  }

  // Schema del bloque `settings` (settings declarativos estilo widgets): el shell lo fetchea en
  // runtime (`/modules/<id>/<settings.schema>`) para renderizar el form genérico de ajustes. En prod
  // el runtime sirve el paquete completo del módulo; aquí, el puente del dev solo copia ese fichero.
  let settingsNote = '';
  const schemaRel = manifest.settings?.schema;
  if (schemaRel) {
    const schemaSrc = join(src, schemaRel);
    if (existsSync(schemaSrc)) {
      mkdirSync(join(dstDir, dirname(schemaRel)), { recursive: true });
      copyFileSync(schemaSrc, join(dstDir, schemaRel));
      settingsNote = ` + ${schemaRel}`;
    } else {
      console.warn(`! módulo ${id}: settings.schema declara ${schemaRel} pero no existe`);
    }
  }
  console.log(`✓ sync ${id}: module.json + ${entry}${iconsNote}${settingsNote} → public/modules/${id}/`);
}
