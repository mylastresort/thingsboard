-- Matches ClaimEntity.java / the existing `claim` table.
-- Skip this if the table already exists from the Java module.

CREATE TABLE IF NOT EXISTS claim (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_time  TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_id     UUID NOT NULL,
    name          VARCHAR(255),
    body          TEXT NOT NULL,
    done          BOOLEAN NOT NULL DEFAULT false,
    assignee_id   UUID,
    tags          JSONB
);

CREATE INDEX IF NOT EXISTS idx_claim_tenant_id ON claim (tenant_id);
CREATE INDEX IF NOT EXISTS idx_claim_tenant_name ON claim (tenant_id, name);
