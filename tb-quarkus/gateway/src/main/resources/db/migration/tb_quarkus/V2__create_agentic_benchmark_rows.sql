CREATE SCHEMA IF NOT EXISTS tb_quarkus_agentic_benchmark;

CREATE TABLE IF NOT EXISTS tb_quarkus_agentic_benchmark.agentic_benchmark_rows (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    subset_name character varying(255) NOT NULL,
    source_file text,
    dataset_record_id bigint,
    subject text,
    question text NOT NULL,
    options jsonb DEFAULT '[]'::jsonb NOT NULL,
    option_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    correct jsonb DEFAULT '[]'::jsonb NOT NULL,
    text_type character varying(255),
    asset_name text,
    relevancy text,
    question_type text,
    trigger_statement text,
    context text,
    raw_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_time bigint NOT NULL,
    updated_time bigint NOT NULL,
    CONSTRAINT agentic_benchmark_rows_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_agentic_benchmark_rows_subset
    ON tb_quarkus_agentic_benchmark.agentic_benchmark_rows (subset_name);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agentic_benchmark_rows_source_record
    ON tb_quarkus_agentic_benchmark.agentic_benchmark_rows (subset_name, dataset_record_id)
    WHERE dataset_record_id IS NOT NULL;
