#!/usr/bin/env node
// erplora module CLI (parcial). Comandos implementados: build, validate.
// Pendientes (stub): pack, sign, publish (ARQUITECTURA.md §7.4).
import { build } from './build.mjs';
import { validate } from './validate.mjs';

const [cmd, moduleDir] = process.argv.slice(2);

const usage = () => {
  console.log('uso: erplora-module <build|validate> <ruta-del-módulo>');
  process.exit(2);
};

if (!cmd || !moduleDir) usage();

try {
  if (cmd === 'build') await build(moduleDir);
  else if (cmd === 'validate') await validate(moduleDir);
  else usage();
} catch (err) {
  console.error('✗ ' + err.message);
  process.exit(1);
}
