-- Vista previa de la siguiente secuencia SIN consumirla. Portado de InvoiceSeriesService.peek_next_number.
-- NOTA: aquí solo devolvemos current_sequence + el siguiente entero crudo (next_sequence).
-- El renderizado del número formateado (format_number con plantilla {prefix}/{year}/{seq:05d}/…)
-- es lógica no declarativa → se calcula en el handler WASM (ver WASM-TODO.md). La UI puede
-- previsualizar con la plantilla devuelta en `format`.
SELECT id              AS series_id,
       current_sequence,
       current_sequence + 1 AS next_sequence,
       format,
       prefix,
       suffix,
       code,
       country_code,
       region_code,
       fiscal_year
FROM invoice_series_series
WHERE id = :series_id AND hub_id = :hub_id AND is_deleted = 0;
