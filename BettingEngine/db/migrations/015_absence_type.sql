-- Migration 015: add absence_type to injury_reports
-- Allows the table to track both injuries and suspensions.
-- Defaults to 'injury' so all existing rows remain valid.

ALTER TABLE injury_reports
    ADD COLUMN absence_type TEXT NOT NULL DEFAULT 'injury'
        CHECK (absence_type IN ('injury', 'suspension'));
