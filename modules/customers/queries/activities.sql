-- Timeline de actividad de un cliente (más reciente primero). Portado de ActivityService.list_activities.
SELECT id, activity_type, title, description, extra_metadata,
       related_object_id, related_object_type, performed_by, created_at
FROM customers_customeractivity
WHERE customer_id = :customer_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC
LIMIT 100;
