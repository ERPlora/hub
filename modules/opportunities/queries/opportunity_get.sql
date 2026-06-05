-- Una oportunidad por id (scope hub_id). Portado de OpportunityService.get_opportunity.
SELECT id, opp_number, customer_name, customer_email, value, probability,
       expected_close_date, stage, close_reason, assigned_to_ref, notes,
       created_at
FROM opportunities_opportunity
WHERE id = :opportunity_id AND hub_id = :hub_id AND is_deleted = 0;
