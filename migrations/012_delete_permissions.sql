-- Split destructive actions into explicit *.delete permission codes.
INSERT OR IGNORE INTO sys_permission (code, name, module) VALUES
('crm.clients.delete', 'crm.clients.delete', 'crm'),
('crm.opportunities.delete', 'crm.opportunities.delete', 'crm'),
('crm.contacts.delete', 'crm.contacts.delete', 'crm'),
('crm.visits.delete', 'crm.visits.delete', 'crm'),
('delivery.roster.delete', 'delivery.roster.delete', 'delivery'),
('delivery.pipeline.delete', 'delivery.pipeline.delete', 'delivery'),
('delivery.handbook.delete', 'delivery.handbook.delete', 'delivery'),
('delivery.interviews.delete', 'delivery.interviews.delete', 'delivery'),
('delivery.settlement.delete', 'delivery.settlement.delete', 'delivery'),
('rms.jobs.delete', 'rms.jobs.delete', 'rms'),
('rms.candidates.delete', 'rms.candidates.delete', 'rms'),
('rms.applications.delete', 'rms.applications.delete', 'rms'),
('dashboard.delete', 'dashboard.delete', 'dashboard'),
('system.users.delete', 'system.users.delete', 'system'),
('system.roles.delete', 'system.roles.delete', 'system');
