-- RMS Offer approval: quote unit (人月/人天/人时) for tax-inclusive quote

ALTER TABLE rms_offer_records ADD COLUMN quote_tax_unit TEXT NOT NULL DEFAULT '';
