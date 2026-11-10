-- RUN ONLY ON A NEW, WRITABLE, TEMPORARY STAGING DATABASE.
-- Run as authorized DBA; replace placeholder account, connection, and paths.
CREATE OR REPLACE DIRECTORY PHCAFE_EXPORT_DIR AS '/backup/ora-datapump-backup';
GRANT READ, WRITE ON DIRECTORY PHCAFE_EXPORT_DIR TO DP_STAGE;
-- Ensure DP_STAGE has CREATE SESSION, CREATE DATABASE LINK, DATAPUMP_EXP_FULL_DATABASE
-- and permissions appropriate for FULL export; grant on STAGING DB, NEVER on PHCAFE.
-- Create private FIXED USER database link while logged into DP_STAGE on staging DB:
-- CREATE DATABASE LINK PHCAFE_RO_LINK CONNECT TO SOURCE_EXPORT_USER
-- IDENTIFIED BY "SOURCE_PASSWORD" USING 'PHCAFE_SOURCE_SERVICE';
-- Do not put credentials in a saved script. Use an interactive protected SQL session.
-- Verify as DP_STAGE:
-- SELECT COUNT(*) FROM all_objects@PHCAFE_RO_LINK WHERE owner='INPLAY';
