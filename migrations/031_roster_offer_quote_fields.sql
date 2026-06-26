-- Quote original fields + billing defaults; monthly_quote_tax stores converted monthly amount.

ALTER TABLE roster_entries ADD COLUMN quote_unit TEXT NOT NULL DEFAULT 'monthly';
ALTER TABLE roster_entries ADD COLUMN quote_amount_tax TEXT NOT NULL DEFAULT '';
ALTER TABLE roster_entries ADD COLUMN monthly_billable_days TEXT NOT NULL DEFAULT '20.67';
ALTER TABLE roster_entries ADD COLUMN daily_billable_hours TEXT NOT NULL DEFAULT '8';

ALTER TABLE rms_offer_records ADD COLUMN quote_amount_tax TEXT NOT NULL DEFAULT '';
ALTER TABLE rms_offer_records ADD COLUMN monthly_billable_days TEXT NOT NULL DEFAULT '20.67';
ALTER TABLE rms_offer_records ADD COLUMN daily_billable_hours TEXT NOT NULL DEFAULT '8';

UPDATE roster_entries
SET quote_amount_tax = monthly_quote_tax
WHERE (quote_amount_tax IS NULL OR quote_amount_tax = '')
  AND monthly_quote_tax IS NOT NULL
  AND monthly_quote_tax != '';

UPDATE rms_offer_records
SET quote_amount_tax = monthly_quote_tax
WHERE (quote_amount_tax IS NULL OR quote_amount_tax = '')
  AND monthly_quote_tax IS NOT NULL
  AND monthly_quote_tax != '';
