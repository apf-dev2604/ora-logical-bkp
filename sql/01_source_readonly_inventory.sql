-- READ ONLY: Execute on existing PHCAFE; save output securely.
SET PAGES 200 LINES 220 TRIMSPOOL ON
SPOOL phcafe_source_inventory.log
SELECT name, dbid, open_mode, controlfile_type, log_mode FROM v$database;
SELECT filename, version FROM v$timezone_file;
SELECT property_name, property_value FROM database_properties WHERE property_name LIKE 'DST_%';
SELECT parameter, value FROM nls_database_parameters WHERE parameter IN ('NLS_CHARACTERSET','NLS_NCHAR_CHARACTERSET');
SELECT owner, object_type, COUNT(*) cnt FROM dba_objects WHERE oracle_maintained='N' GROUP BY owner, object_type ORDER BY owner, object_type;
SELECT username, default_tablespace, temporary_tablespace, oracle_maintained FROM dba_users WHERE oracle_maintained='N' ORDER BY username;
SELECT grantee, granted_role FROM dba_role_privs WHERE granted_role='DATAPUMP_EXP_FULL_DATABASE';
SELECT username, temporary_tablespace FROM dba_users WHERE username = UPPER('&SOURCE_EXPORT_USER');
SELECT tablespace_name, contents, extent_management FROM dba_tablespaces WHERE contents='TEMPORARY';
SELECT owner, COUNT(*) table_count FROM dba_tables WHERE owner='INPLAY' GROUP BY owner;
SELECT owner, object_type, COUNT(*) cnt FROM dba_objects WHERE owner='INPLAY' GROUP BY owner, object_type ORDER BY object_type;
SELECT owner, object_name, object_type FROM dba_objects WHERE owner='INPLAY' AND status='INVALID' ORDER BY object_type, object_name;
SPOOL OFF
