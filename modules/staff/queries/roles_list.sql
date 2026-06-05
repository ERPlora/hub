-- Roles de staff activos del hub. Runtime inyecta :hub_id.
-- Portado de StaffService.list_roles. member_count = miembros activos no borrados con el rol.
SELECT r.id, r.name, r.description, r.color, r."order", r.is_active,
       (SELECT COUNT(*) FROM staff_member m
        WHERE m.role_id = r.id AND m.hub_id = r.hub_id
          AND m.is_deleted = 0 AND m.status = 'active') AS member_count
FROM staff_role r
WHERE r.hub_id = :hub_id AND r.is_deleted = 0 AND r.is_active = 1
ORDER BY r."order" ASC, r.name ASC;
