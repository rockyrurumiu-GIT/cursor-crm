-- Grant delivery.employee_files.delete to roles that already have write (matches DELETE_PERMISSION_COMPAT_PAIRS).

INSERT OR IGNORE INTO sys_permission (code, name, module) VALUES
('delivery.employee_files.delete', 'delivery.employee_files.delete', 'delivery');

INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id)
SELECT rp.role_id, p_delete.id
FROM sys_role_permission rp
JOIN sys_permission p_source ON p_source.id = rp.permission_id
JOIN sys_permission p_delete ON p_delete.code = 'delivery.employee_files.delete'
WHERE p_source.code = 'delivery.employee_files.write';

INSERT INTO sys_role_data_scope (role_id, resource_code, action, scope_type, created_at, updated_at)
SELECT rp.role_id, 'delivery.employee_files', 'delete', src.scope_type, datetime('now'), datetime('now')
FROM sys_role_permission rp
JOIN sys_permission p ON p.id = rp.permission_id
JOIN sys_role_data_scope src
  ON src.role_id = rp.role_id
 AND src.resource_code = 'delivery.employee_files'
 AND src.action = 'write'
WHERE p.code = 'delivery.employee_files.write'
AND NOT EXISTS (
    SELECT 1 FROM sys_role_data_scope existing
    WHERE existing.role_id = rp.role_id
      AND existing.resource_code = 'delivery.employee_files'
      AND existing.action = 'delete'
);
