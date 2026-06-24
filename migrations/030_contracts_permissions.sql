-- Split contract file access out of crm.opportunities.* into dedicated crm.contracts.*.
-- Plan B (inherit): grant new codes to any role that already had the equivalent opportunities access,
-- preserving current behavior (download was previously gated by .read; delete by .write).

INSERT OR IGNORE INTO sys_permission (code, name, module) VALUES
('crm.contracts.read', 'crm.contracts.read', 'crm'),
('crm.contracts.write', 'crm.contracts.write', 'crm'),
('crm.contracts.delete', 'crm.contracts.delete', 'crm'),
('crm.contracts.download', 'crm.contracts.download', 'crm');

-- Roles with crm.opportunities.read inherit contracts read + download.
INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id)
SELECT rp.role_id, p_new.id
FROM sys_role_permission rp
JOIN sys_permission p_src ON p_src.id = rp.permission_id
JOIN sys_permission p_new ON p_new.code IN ('crm.contracts.read', 'crm.contracts.download')
WHERE p_src.code = 'crm.opportunities.read';

-- Roles with crm.opportunities.write inherit contracts write + delete.
INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id)
SELECT rp.role_id, p_new.id
FROM sys_role_permission rp
JOIN sys_permission p_src ON p_src.id = rp.permission_id
JOIN sys_permission p_new ON p_new.code IN ('crm.contracts.write', 'crm.contracts.delete')
WHERE p_src.code = 'crm.opportunities.write';
