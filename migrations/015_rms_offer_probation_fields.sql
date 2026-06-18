-- RMS Offer approval: replace salary_months with probation fields

ALTER TABLE rms_offer_records RENAME COLUMN salary_months TO probation_days;

ALTER TABLE rms_offer_records ADD COLUMN probation_discount_months TEXT NOT NULL DEFAULT '';
