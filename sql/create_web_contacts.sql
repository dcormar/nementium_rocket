-- Script SQL para crear la tabla WEB_CONTACTS en Supabase
-- Tabla para almacenar contactos recibidos desde formularios web
-- El agente email-contact-helper procesa estos contactos de forma asíncrona

CREATE TABLE IF NOT EXISTS web_contacts (
    id BIGSERIAL PRIMARY KEY,
    source_url TEXT,                          -- URL donde se rellenó el formulario
    name TEXT NOT NULL,                       -- Nombre del contacto
    email TEXT NOT NULL,                      -- Email del contacto
    phone TEXT,                               -- Teléfono (normalizado)
    company TEXT,                             -- Empresa del contacto
    message TEXT,                             -- Mensaje original
    status TEXT DEFAULT 'new',                -- new, processing, emailed, error
    prospecting_json JSONB DEFAULT '{}',      -- Resultado de la prospección online
    email_sent_at TIMESTAMPTZ,                -- Timestamp de envío de email
    error TEXT,                               -- Mensaje de error si status='error'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para búsquedas frecuentes
CREATE INDEX IF NOT EXISTS idx_web_contacts_status ON web_contacts(status);
CREATE INDEX IF NOT EXISTS idx_web_contacts_email ON web_contacts(email);
CREATE INDEX IF NOT EXISTS idx_web_contacts_created_at ON web_contacts(created_at);

-- Trigger para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_web_contacts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_web_contacts_updated_at ON web_contacts;
CREATE TRIGGER trigger_web_contacts_updated_at
    BEFORE UPDATE ON web_contacts
    FOR EACH ROW
    EXECUTE PROCEDURE update_web_contacts_updated_at();

-- Comentarios
COMMENT ON TABLE web_contacts IS 'Contactos recibidos desde formularios web, procesados por el agente email-contact-helper';
COMMENT ON COLUMN web_contacts.source_url IS 'URL del formulario donde se recibió el contacto';
COMMENT ON COLUMN web_contacts.name IS 'Nombre del contacto';
COMMENT ON COLUMN web_contacts.email IS 'Email del contacto (validado y normalizado)';
COMMENT ON COLUMN web_contacts.phone IS 'Teléfono del contacto (normalizado)';
COMMENT ON COLUMN web_contacts.company IS 'Empresa del contacto';
COMMENT ON COLUMN web_contacts.message IS 'Mensaje original enviado por el contacto';
COMMENT ON COLUMN web_contacts.status IS 'Estado del procesamiento: new, processing, emailed, error';
COMMENT ON COLUMN web_contacts.prospecting_json IS 'Resultado estructurado de la prospección online (empresa, persona, señales, fit)';
COMMENT ON COLUMN web_contacts.email_sent_at IS 'Timestamp cuando se envió el email de notificación';
COMMENT ON COLUMN web_contacts.error IS 'Descripción del error si el procesamiento falló';

-- Habilitar RLS (Row Level Security) - opcional, ajustar según necesidades
-- ALTER TABLE web_contacts ENABLE ROW LEVEL SECURITY;
