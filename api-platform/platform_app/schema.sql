PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('customer','admin')),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wallets (
 user_id TEXT PRIMARY KEY REFERENCES users(id),
 available INTEGER NOT NULL DEFAULT 0 CHECK(available >= 0),
 reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0)
);
CREATE TABLE IF NOT EXISTS api_keys (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
 token_hash TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL, daily_limit INTEGER NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT, revoked_at TEXT, last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS budgets (
 key_id TEXT NOT NULL REFERENCES api_keys(id), period TEXT NOT NULL,
 reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
 spent INTEGER NOT NULL DEFAULT 0 CHECK(spent >= 0), PRIMARY KEY(key_id,period)
);
CREATE TABLE IF NOT EXISTS prices (
 id TEXT PRIMARY KEY, model TEXT NOT NULL, version INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','published')),
 rule TEXT NOT NULL, created_at TEXT NOT NULL, published_at TEXT,
 author_id TEXT REFERENCES users(id), UNIQUE(model,version)
);
CREATE TABLE IF NOT EXISTS quotes (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 model TEXT NOT NULL, input_json TEXT NOT NULL, input_hash TEXT NOT NULL,
 project_ref TEXT NOT NULL, price_id TEXT NOT NULL REFERENCES prices(id),
 snapshot TEXT NOT NULL, amount INTEGER NOT NULL, created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, accepted_job_id TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 key_id TEXT NOT NULL REFERENCES api_keys(id), quote_id TEXT UNIQUE NOT NULL REFERENCES quotes(id),
 intent_id TEXT NOT NULL, request_hash TEXT NOT NULL, period TEXT NOT NULL,
 status TEXT NOT NULL, funds_status TEXT NOT NULL, hold INTEGER NOT NULL,
 charge INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 submission_id TEXT UNIQUE, result TEXT, error TEXT,
 UNIQUE(user_id,intent_id)
);
CREATE TABLE IF NOT EXISTS idempotency (
 user_id TEXT NOT NULL REFERENCES users(id), operation TEXT NOT NULL,
 idem_key TEXT NOT NULL, body_hash TEXT NOT NULL, resource_id TEXT NOT NULL,
 PRIMARY KEY(user_id,operation,idem_key)
);
CREATE TABLE IF NOT EXISTS outbox (
 job_id TEXT PRIMARY KEY REFERENCES jobs(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), amount_fen INTEGER NOT NULL,
 state TEXT NOT NULL, created_at TEXT NOT NULL, paid_at TEXT, provider_tx TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS vouchers (
 id TEXT PRIMARY KEY, event_key TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL, reference TEXT NOT NULL, created_at TEXT NOT NULL,
 available_after INTEGER NOT NULL, reserved_after INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS postings (
 id INTEGER PRIMARY KEY, voucher_id TEXT NOT NULL REFERENCES vouchers(id),
 account TEXT NOT NULL, amount INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id TEXT PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES users(id),
 action TEXT NOT NULL, resource_id TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_vouchers_update BEFORE UPDATE ON vouchers
 BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER IF NOT EXISTS immutable_vouchers_delete BEFORE DELETE ON vouchers
 BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER IF NOT EXISTS immutable_postings_update BEFORE UPDATE ON postings
 BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER IF NOT EXISTS immutable_postings_delete BEFORE DELETE ON postings
 BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER IF NOT EXISTS immutable_published_prices BEFORE UPDATE ON prices
 WHEN OLD.state='published' BEGIN SELECT RAISE(ABORT,'published price is immutable'); END;
CREATE INDEX IF NOT EXISTS jobs_user_time ON jobs(user_id,created_at);
CREATE INDEX IF NOT EXISTS vouchers_user_time ON vouchers(user_id,created_at);

CREATE TABLE IF NOT EXISTS commercial_wallets (
 user_id TEXT PRIMARY KEY REFERENCES users(id),
 available INTEGER NOT NULL DEFAULT 0 CHECK(available>=0),
 reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0)
);
CREATE TABLE IF NOT EXISTS credit_grants (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 actor_id TEXT NOT NULL REFERENCES users(id), amount INTEGER NOT NULL,
 note TEXT NOT NULL, created_at TEXT NOT NULL, voucher_id TEXT REFERENCES vouchers(id)
);
CREATE TABLE IF NOT EXISTS redeem_codes (
 id TEXT PRIMARY KEY, code_hash TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>0), batch TEXT NOT NULL,
 author_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, bound_user_id TEXT REFERENCES users(id),
 redeemed_by TEXT REFERENCES users(id), redeemed_at TEXT, revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS gateway_prices (
 id TEXT PRIMARY KEY, model TEXT NOT NULL, version INTEGER NOT NULL,
 rule TEXT NOT NULL, author_id TEXT REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(model,version)
);
CREATE TRIGGER IF NOT EXISTS immutable_gateway_prices_update BEFORE UPDATE ON gateway_prices
 BEGIN SELECT RAISE(ABORT,'published price is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_gateway_prices_delete BEFORE DELETE ON gateway_prices
 BEGIN SELECT RAISE(ABORT,'published price is immutable'); END;
CREATE TABLE IF NOT EXISTS gateway_quotes (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), model TEXT NOT NULL,
 input_json TEXT NOT NULL, price_id TEXT NOT NULL REFERENCES gateway_prices(id),
 snapshot TEXT NOT NULL, amount INTEGER NOT NULL, project_ref TEXT NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL, accepted_job_id TEXT
);
CREATE TABLE IF NOT EXISTS gateway_jobs (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 key_id TEXT NOT NULL REFERENCES api_keys(id), quote_id TEXT UNIQUE NOT NULL REFERENCES gateway_quotes(id),
 intent_id TEXT NOT NULL, body_hash TEXT NOT NULL, period TEXT NOT NULL,
 status TEXT NOT NULL, hold INTEGER NOT NULL, charge INTEGER NOT NULL DEFAULT 0,
 cost INTEGER, usage_json TEXT, result_json TEXT, upstream_id TEXT, error TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(user_id,intent_id)
);
CREATE INDEX IF NOT EXISTS gateway_user_time ON gateway_jobs(user_id,created_at);
CREATE TABLE IF NOT EXISTS gateway_files (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
 size INTEGER NOT NULL, duration_seconds INTEGER, total_frames INTEGER, created_at TEXT NOT NULL
);

-- Additive tables preserve existing accounts and immutable money records.
CREATE TABLE IF NOT EXISTS user_access (
 user_id TEXT PRIMARY KEY REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
 must_change_password INTEGER NOT NULL DEFAULT 0 CHECK(must_change_password IN (0,1))
);
CREATE TABLE IF NOT EXISTS funding_settings (
 id INTEGER PRIMARY KEY CHECK(id=1), contact TEXT NOT NULL, instructions TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS funding_receipts (
 id TEXT PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES users(id),
 user_id TEXT REFERENCES users(id), kind TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
 channel TEXT NOT NULL, payment_ref TEXT UNIQUE, note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS funding_sources (
 resource_id TEXT PRIMARY KEY, receipt_id TEXT NOT NULL REFERENCES funding_receipts(id)
);
CREATE TABLE IF NOT EXISTS redeem_replacements (
 old_code_id TEXT PRIMARY KEY REFERENCES redeem_codes(id),
 new_code_id TEXT UNIQUE NOT NULL REFERENCES redeem_codes(id)
);
CREATE TRIGGER IF NOT EXISTS immutable_funding_update BEFORE UPDATE ON funding_receipts
 BEGIN SELECT RAISE(ABORT,'immutable funding receipt'); END;
CREATE TRIGGER IF NOT EXISTS immutable_funding_delete BEFORE DELETE ON funding_receipts
 BEGIN SELECT RAISE(ABORT,'immutable funding receipt'); END;

CREATE TABLE IF NOT EXISTS gateway_voices (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), name TEXT NOT NULL,
 provider_voice_id TEXT NOT NULL, target_model TEXT NOT NULL, provider_scope TEXT NOT NULL,
 language TEXT NOT NULL, tags_json TEXT NOT NULL, status TEXT NOT NULL,
 clone_job_id TEXT UNIQUE REFERENCES gateway_jobs(id), sample_job_id TEXT REFERENCES gateway_jobs(id), sample_file TEXT,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS voices_owner ON gateway_voices(user_id,status);
CREATE TABLE IF NOT EXISTS gateway_voice_tickets (
 token_hash TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES gateway_files(id),
 user_id TEXT NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL
);
