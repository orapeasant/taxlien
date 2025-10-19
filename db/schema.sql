CREATE TABLE IF NOT EXISTS municipalities(
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tax_bills(
  id BIGSERIAL PRIMARY KEY,
  municipality_slug TEXT NOT NULL,
  collection TEXT NOT NULL,
  bill_id TEXT,
  owner_name TEXT,
  parcel_id TEXT,
  property_address TEXT,
  status TEXT,
  amount_due NUMERIC,
  amount_paid NUMERIC,
  due_date DATE,
  detail_url TEXT,
  source_url TEXT NOT NULL,
  extracted_at TIMESTAMP NOT NULL DEFAULT NOW(),
  raw_snapshot_path TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_bill
ON tax_bills(municipality_slug, collection, COALESCE(bill_id,''), COALESCE(parcel_id,''), COALESCE(owner_name,''));
