-- Data Quality Issues table — records that failed validation before Silver insertion
CREATE TABLE IF NOT EXISTS silver.data_quality_issues (
    id              SERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL,
    error_messages  TEXT[] NOT NULL,
    raw_record      JSONB,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
