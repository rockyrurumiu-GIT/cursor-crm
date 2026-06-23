-- Decommission delivery pipeline (replaced by RMS pipeline tab).

DELETE FROM sys_role_permission
WHERE permission_id IN (
    SELECT id FROM sys_permission WHERE code LIKE 'delivery.pipeline.%'
);

DELETE FROM sys_permission WHERE code LIKE 'delivery.pipeline.%';

DELETE FROM dashboard_widgets WHERE source_key = 'delivery_pipeline_entries';

DROP TABLE IF EXISTS delivery_pipeline_insight_demands;
DROP TABLE IF EXISTS delivery_pipeline_entries;
