-- Gold Schema Proposals Table
-- Stores AI-generated proposals for new Gold tables or columns
-- Status: pending_approval, approved, rejected, implemented

CREATE TABLE IF NOT EXISTS gold.schema_proposals (
    id                      SERIAL PRIMARY KEY,
    proposal_type           TEXT NOT NULL,              -- 'new_table' or 'new_columns'
    target_table            TEXT NOT NULL,              -- Table name (existing or proposed)
    proposed_ddl            TEXT,                       -- CREATE TABLE statement if new_table
    proposed_columns        JSONB,                      -- Array of {name, type, description} if new_columns
    silver_to_gold_mapping  JSONB,                      -- Detailed mapping: source tables, column mappings, filters, joins
    business_question       TEXT NOT NULL,              -- The question that triggered this proposal
    silver_tables_queried   JSONB,                      -- Which Silver tables were used
    sample_data_returned    JSONB,                      -- Sample of what Silver returned
    rationale               TEXT,                       -- AI explanation for this proposal
    proposed_sql            TEXT,                       -- The SQL query that would populate this
    status                  TEXT DEFAULT 'pending_approval',  -- pending_approval, approved, rejected, implemented
    reviewed_by             TEXT,                       -- Engineer who reviewed
    review_notes            TEXT,                       -- Reviewer comments
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at             TIMESTAMP,
    implemented_at          TIMESTAMP
);

-- Index for quick lookup of pending proposals
CREATE INDEX IF NOT EXISTS idx_schema_proposals_status 
    ON gold.schema_proposals(status) 
    WHERE status = 'pending_approval';
