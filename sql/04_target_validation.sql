-- RUN ON THE RESTORED TARGET AFTER impdp AND REVIEW AGAINST SOURCE INVENTORY.
SET PAGES 200 LINES 220 TRIMSPOOL ON
SPOOL phcafe_target_validation.log
SELECT name, open_mode FROM v$database;
SELECT filename, version FROM v$timezone_file;
SELECT owner, object_type, COUNT(*) cnt FROM dba_objects WHERE oracle_maintained='N' GROUP BY owner, object_type ORDER BY owner, object_type;
SELECT owner, object_type, COUNT(*) cnt FROM dba_objects WHERE owner='INPLAY' GROUP BY owner, object_type ORDER BY object_type;
SELECT owner, object_name, object_type FROM dba_objects WHERE owner='INPLAY' AND status='INVALID' ORDER BY object_type, object_name;
SELECT username, account_status, default_tablespace FROM dba_users WHERE oracle_maintained='N' ORDER BY username;
SELECT owner, table_name FROM dba_tables WHERE owner='INPLAY' ORDER BY table_name;
SPOOL OFF
-- Add exact row counts for critical INPLAY tables and independent application checks.
