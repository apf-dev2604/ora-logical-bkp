-- RUN ONLY ON THE NEW, WRITABLE TARGET ORACLE 19c DATABASE.
-- First create OS directory /backup/ora-datapump-backup and make Oracle able to write there.
CREATE OR REPLACE DIRECTORY PHCAFE_IMPORT_DIR AS '/backup/ora-datapump-backup';
GRANT READ, WRITE ON DIRECTORY PHCAFE_IMPORT_DIR TO DP_IMPORT;
-- Ensure DP_IMPORT has DATAPUMP_IMP_FULL_DATABASE and required CREATE SESSION.
-- Precreate needed tablespaces with valid target filesystem paths when necessary;
-- evaluate REMAP_TABLESPACE and metadata conflicts before actual import.
