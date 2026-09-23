CREATE TABLE links (
    id              BIGSERIAL PRIMARY KEY,
    short_code      VARCHAR(16) NOT NULL UNIQUE,
    long_url        TEXT NOT NULL,
    is_custom_alias BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NULL,
    click_count     BIGINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX idx_links_short_code ON links (short_code);
CREATE INDEX idx_links_expires_at ON links (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE click_events (
    id          BIGSERIAL PRIMARY KEY,
    short_code  VARCHAR(16) NOT NULL REFERENCES links(short_code),
    clicked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_hint     TEXT NULL
);

CREATE INDEX idx_click_events_short_code_clicked_at ON click_events (short_code, clicked_at DESC);
