-- Dashboard scope (crm vs rms) and per-tab layout for RMS templates
ALTER TABLE dashboard_dashboards ADD COLUMN scope TEXT NOT NULL DEFAULT 'crm';
ALTER TABLE dashboard_tabs ADD COLUMN layout_json TEXT NOT NULL DEFAULT '{}';
