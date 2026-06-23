-- 部门类型：通用 / 业务 / 职能（替代 sales / delivery / finance）
UPDATE sys_dept SET dept_type = 'business' WHERE dept_type IN ('sales', 'delivery');
UPDATE sys_dept SET dept_type = 'functional' WHERE dept_type = 'finance';
