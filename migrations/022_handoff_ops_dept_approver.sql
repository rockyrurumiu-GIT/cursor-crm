-- 待审交接单审批人统一为经营部负责人
UPDATE handoff_requests
SET delivery_owner_user_id = (
    SELECT d.head_user_id
    FROM sys_dept d
    WHERE d.status = 'active'
      AND d.head_user_id IS NOT NULL
      AND (d.name = '经营部' OR d.code IN ('OPERATIONS', 'OPS', 'OPERATING'))
    ORDER BY CASE WHEN d.name = '经营部' THEN 0 ELSE 1 END, d.id
    LIMIT 1
),
delivery_owner = (
    SELECT u.username
    FROM sys_dept d
    JOIN sys_user u ON u.id = d.head_user_id AND u.status = 'active'
    WHERE d.status = 'active'
      AND (d.name = '经营部' OR d.code IN ('OPERATIONS', 'OPS', 'OPERATING'))
    ORDER BY CASE WHEN d.name = '经营部' THEN 0 ELSE 1 END, d.id
    LIMIT 1
)
WHERE status = 'pending_review'
  AND EXISTS (
    SELECT 1
    FROM sys_dept d
    WHERE d.status = 'active'
      AND d.head_user_id IS NOT NULL
      AND (d.name = '经营部' OR d.code IN ('OPERATIONS', 'OPS', 'OPERATING'))
  );
