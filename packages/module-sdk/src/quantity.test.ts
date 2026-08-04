import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  QUANTITY_SCALE,
  toMicro,
  fromMicro,
  parseQuantity,
  formatQuantity,
  onGrid,
} from './quantity.ts';

test('cantidad lógica y wire 10⁶ conservan exactamente el valor', () => {
  assert.equal(QUANTITY_SCALE, 1_000_000);
  assert.equal(toMicro(0.5), 500_000);
  assert.equal(toMicro(0.1 + 0.2), 300_000);
  assert.equal(fromMicro(2_500_000), 2.5);
});

test('parseQuantity acepta coma o punto y nunca trunca precisión', () => {
  assert.equal(parseQuantity('0,125'), 125_000);
  assert.equal(parseQuantity('123.456789'), 123_456_789);
  assert.equal(parseQuantity(' 2 '), 2_000_000);
  assert.equal(parseQuantity('0.1234567'), null);
  assert.equal(parseQuantity('-1'), null);
  assert.equal(parseQuantity(''), null);
  assert.equal(parseQuantity('9007199255'), null, 'el wire JSON solo admite enteros seguros');
});

test('formatQuantity no introduce ceros ni notación científica', () => {
  assert.equal(formatQuantity(2_000_000), '2');
  assert.equal(formatQuantity(1_250_000), '1.25');
  assert.equal(formatQuantity(1), '0.000001');
  assert.equal(formatQuantity(-500_000), '-0.5');
});

test('onGrid valida el incremento sin corregir la cantidad', () => {
  assert.equal(onGrid(500_000, 1_000), true);
  assert.equal(onGrid(500, 1_000), false);
  assert.equal(onGrid(500_000, 1_000_000), false);
  assert.equal(onGrid(500_000, 0), true);
});
