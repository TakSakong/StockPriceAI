-- StockPriceAI 로컬 개발용 초기 스키마
-- 프로덕션(RDS)에서는 Alembic 마이그레이션이 이 역할을 대신함

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id  UUID REFERENCES users(id) ON DELETE CASCADE,
    ticker   VARCHAR(20) NOT NULL,
    memo     TEXT,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS predictions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker      VARCHAR(20) NOT NULL,
    signal      VARCHAR(10) NOT NULL,
    up_prob     FLOAT NOT NULL,
    model_type  VARCHAR(50),
    complexity  FLOAT,
    xgb_weight  FLOAT,
    lstm_weight FLOAT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scan_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    status      VARCHAR(20) DEFAULT 'pending',
    total       INT,
    processed   INT DEFAULT 0,
    sector      VARCHAR(100),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scan_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES scan_jobs(id) ON DELETE CASCADE,
    ticker          VARCHAR(20) NOT NULL,
    composite_score FLOAT,
    up_prob         FLOAT,
    signal          VARCHAR(10),
    sector          VARCHAR(100),
    est_upside      FLOAT,
    cached_at       TIMESTAMPTZ DEFAULT NOW()
);
