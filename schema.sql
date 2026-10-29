-- Chama Clínica: esquema PostgreSQL para Supabase ou Neon.
-- O Flask também executa db.create_all() automaticamente no primeiro start.

CREATE TABLE IF NOT EXISTS calls (
    id BIGSERIAL PRIMARY KEY,
    patient_name VARCHAR(100) NOT NULL,
    registration VARCHAR(40) NOT NULL,
    room VARCHAR(60) NOT NULL DEFAULT 'Consultório',
    status VARCHAR(20) NOT NULL DEFAULT 'aguardando',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    called_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_calls_status CHECK (status IN ('aguardando', 'chamado', 'finalizado', 'cancelado'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_call ON calls (status) WHERE status = 'chamado';
CREATE INDEX IF NOT EXISTS ix_calls_waiting_order ON calls (status, created_at, id);

-- Opcional: manter updated_at atualizado para alterações feitas diretamente no banco.
CREATE OR REPLACE FUNCTION set_calls_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS calls_updated_at_trigger ON calls;
CREATE TRIGGER calls_updated_at_trigger
BEFORE UPDATE ON calls
FOR EACH ROW EXECUTE FUNCTION set_calls_updated_at();
