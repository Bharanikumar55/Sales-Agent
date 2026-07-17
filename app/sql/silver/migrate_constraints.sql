-- Drop old silver.dim_contact UNIQUE(name) constraint if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'dim_contact'
          AND table_schema = 'silver'
          AND constraint_type = 'UNIQUE'
          AND constraint_name = 'dim_contact_name_key'
    ) THEN
        ALTER TABLE silver.dim_contact DROP CONSTRAINT dim_contact_name_key;
    END IF;
END $$;

-- Add silver.dim_contact composite UNIQUE(name, account_name) if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'dim_contact'
          AND table_schema = 'silver'
          AND constraint_type = 'UNIQUE'
          AND constraint_name = 'dim_contact_name_account_unique'
    ) THEN
        ALTER TABLE silver.dim_contact ADD CONSTRAINT dim_contact_name_account_unique 
        UNIQUE ("contact_name", "account_name");
    END IF;
END $$;
