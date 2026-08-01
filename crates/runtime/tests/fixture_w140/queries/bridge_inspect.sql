SELECT
  erp_date(:at) AS date,
  erp_timefmt(erp_extract('hour', :at), erp_extract('minute', :at)) AS time,
  erp_dow_mon0(:at) AS dow;
