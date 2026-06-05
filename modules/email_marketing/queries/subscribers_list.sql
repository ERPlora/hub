-- Suscriptores de una lista (scope hub_id). Runtime inyecta :hub_id.
-- Portado de la consulta de suscriptores de EmailMarketingService. Filtro opcional por
-- status (:status = '' → todos).
SELECT id, list_id, email, first_name, last_name, status,
       subscribed_at, unsubscribed_at
FROM email_marketing_subscriber
WHERE hub_id = :hub_id AND is_deleted = 0
  AND list_id = :list_id
  AND (:status = '' OR status = :status)
ORDER BY email ASC;
