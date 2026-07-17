-- Create schemas if they don't exist
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;

-- Create bronze raw data table
CREATE TABLE IF NOT EXISTS bronze.raw_ingestion (
    id SERIAL PRIMARY KEY,
    source VARCHAR(255),
    data_type VARCHAR(50),
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create silver processed data table
CREATE TABLE IF NOT EXISTS silver.processed_data (
    id SERIAL PRIMARY KEY,
    source VARCHAR(255),
    classification_method VARCHAR(50),
    processed_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
