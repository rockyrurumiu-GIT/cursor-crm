-- Backfill candidate master target fields from each candidate's latest recommendation.
UPDATE rms_candidates
SET
  target_job_id = (
    SELECT a.job_id
    FROM rms_applications a
    WHERE a.candidate_id = rms_candidates.id
    ORDER BY a.recommended_at DESC, a.id DESC
    LIMIT 1
  ),
  target_client_id = (
    SELECT a.client_id
    FROM rms_applications a
    WHERE a.candidate_id = rms_candidates.id
    ORDER BY a.recommended_at DESC, a.id DESC
    LIMIT 1
  )
WHERE target_job_id IS NULL
  AND target_client_id IS NULL
  AND EXISTS (
    SELECT 1 FROM rms_applications a WHERE a.candidate_id = rms_candidates.id
  );
