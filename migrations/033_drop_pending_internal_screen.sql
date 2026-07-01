-- Merge legacy pending_internal_screen into recommended (待内筛).
UPDATE rms_applications
SET status = 'recommended',
    current_stage = 'recommended'
WHERE status = 'pending_internal_screen'
   OR current_stage = 'pending_internal_screen';
