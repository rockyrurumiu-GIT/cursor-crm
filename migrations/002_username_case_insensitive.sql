CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_user_username_lower ON sys_user(LOWER(username));
