-- Edición de miembro del staff. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de StaffService.update_staff_member. Patrón COALESCE: un bind NULL deja el valor
-- actual sin tocar (parcial), salvo los campos siempre presentes que el SDK normaliza.
UPDATE staff_member
SET first_name      = COALESCE(:first_name, first_name),
    last_name       = COALESCE(:last_name, last_name),
    email           = COALESCE(:email, email),
    phone           = COALESCE(:phone, phone),
    role_id         = COALESCE(:role_id, role_id),
    status          = COALESCE(:status, status),
    hire_date       = COALESCE(:hire_date, hire_date),
    hourly_rate     = COALESCE(:hourly_rate, hourly_rate),
    commission_rate = COALESCE(:commission_rate, commission_rate),
    is_bookable     = COALESCE(:is_bookable, is_bookable),
    bio             = COALESCE(:bio, bio),
    specialties     = COALESCE(:specialties, specialties),
    notes           = COALESCE(:notes, notes),
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE id = :staff_id AND hub_id = :hub_id AND is_deleted = 0;
