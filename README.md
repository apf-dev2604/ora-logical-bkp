# PHCAFE Oracle 19c — Read-only Source to Data Pump S3 Backup

## Purpose and limits

This is a **logical Oracle Data Pump FULL export over NETWORK_LINK**, not an RMAN backup and not a cold file copy. It reads the existing PHCAFE `OPEN READ ONLY` instance over Oracle Net, and **the Data Pump job/master table runs in a separate writable Oracle 19c staging database**. The source is not restarted, mounted, or modified by this kit. The dumps can be imported into a **new** Oracle 19c database without the old PHCAFE redo or backup control file.

**This is not a full server clone or a guarantee of an error-free import.** System-managed Oracle objects and certain external dependencies are outside Data Pump. User accounts, roles, grants, INPLAY and other application objects are exportable when proper full-export privileges exist. Preserve wallets/keys, external file contents, listener/tnsnames, Oracle home patch inventory, DST version and init parameter inventory separately. Database links may need their credentials reconfigured. Recompile invalid objects, review scheduled jobs, external integrations, UTL_FILE paths, directory objects, TDE and edition-specific features on target.

The original 47 datafiles occupy 598.57 GiB, **not necessarily the Data Pump dump size**. Space is based on actual table data/LOBs and chosen compression. `COMPRESSION=METADATA_ONLY` does not compress table data and avoids Advanced Compression entitlement assumptions. 2 GiB dump segments are easy to upload/retry and verify.

## Destination

- S3 bucket: `oracle-data-migration-backup-454983519280-ap-southeast-1`
- Region: `ap-southeast-1`
- S3 prefix: `ora-datapump-backup/PHCAFE/BASELINE_20261110/`
- Local staging directory: `/backup/ora-datapump-backup` **on an attached, encrypted local EBS filesystem**, never on S3 FUSE.
- Oracle directory object: `PHCAFE_EXPORT_DIR`, created **on temporary writable staging database** only.

Use a new prefix, local directory, parfile and job name for each additional baseline; never overwrite a completed set.

## Setup

1. Preserve existing EC2/EBS snapshots as an independent physical fallback. Leave the only running PHCAFE replica untouched.
2. Provision a **separate writable Oracle 19c staging database** with a filesystem sized for exported data, plus sufficient disk for temporary database tablespaces. Make sure staging database is compatible with source architecture, character set and DST; avoid changing source TZ.
3. On PHCAFE **run only read-only checks** in `sql/01_source_readonly_inventory.sql`. The source DB link user must ALREADY have sufficient privileges (including full export role for FULL=Y) and a **locally managed temporary tablespace**. If no such pre-existing source account exists, do not attempt grants/CREATE on read-only source; obtain an authorized route/account first.
4. Ensure Oracle Net between staging and PHCAFE is private and encrypted (e.g. Oracle native network encryption/TLS, per approved configuration). Data Pump over unencrypted DB link transfers data in clear text.
5. On staging EC2, create `/backup/ora-datapump-backup`, owned by Oracle user. As an authorized staging DBA run `sql/02_stage_setup.sql` after replacing `DP_STAGE` with actual staging export account. Provide staging account with `DATAPUMP_EXP_FULL_DATABASE` and `CREATE DATABASE LINK`. Create a **private fixed-user** database link `PHCAFE_RO_LINK` as that staging account in an interactive protected SQL*Plus session using existing authorized source account. Do not save real database link credentials in shell history or scripts. Check `SELECT COUNT(*) FROM all_objects@PHCAFE_RO_LINK WHERE owner='INPLAY';`
6. Install package on staging, `python3 -m pip install --user -r requirements.txt`, `cp config.example.json config.json`, `chmod 600 config.json`, update Gmail username/recipients and password file. Confirm environment: `aws sts get-caller-identity`, IAM allows S3 GetObject, PutObject, ListBucket and HeadBucket for target prefix; python uses instance role, not access keys in config.
7. `python3 dr_manager.py --config config.json --test-s3` then test Gmail by running `python3 dr_manager.py --config config.json --alert 'PHCAFE SMTP test notification'` (this is deliberately labelled alert).
8. Set up Oracle secure external password store so `DP_STAGE_CONNECT='/@DPSTAGE'` authenticates the **staging** account. Alternatively run `expdp` manually with a prompt; do not put passwords in process arguments.
9. Ensure dump directory is empty. Run `export DP_STAGE_CONNECT='/@DPSTAGE'; ./run_export.sh` on staging. It runs `expdp`, stops if the utility fails, and then uploads and **reads back each S3 dump** to compare full SHA256 before marking transfer verified. A failing export/upload sends a notification. Do not interrupt/overwrite a still-running Data Pump job; Data Pump jobs have their own attach/restart semantics.
10. Store the source inventory SQL spool, patch inventory, Data Pump export log, and non-database external dependencies securely alongside dump metadata when ready. Do not put secrets in the package or S3.

## Restore test on separate Oracle Linux 8 / Oracle 19c server

1. Install supported 19c RU on fresh Oracle Linux 8, matching required source character set/NCHAR settings. **Check source vs target timezone-file VERSION** and prepare target to same-or-newer supported DST to avoid `ORA-39405`.
2. Create fresh **writable** target Oracle database (not the old PHCAFE control file or datafiles). Prevent application network access and job execution until validated.
3. Create a local encrypted EBS filesystem `/backup/ora-datapump-backup` with sufficient space, and create `PHCAFE_IMPORT_DIR` using `sql/03_target_setup.sql`. Prepare source-compatible tablespaces and adjust file paths or remapping as necessary.
4. Configure target `config.json` with same bucket/prefix and local dump directory, AWS read access, and optional Gmail. Run `python3 dr_manager.py --config config.json --download`. Every S3 file is SHA256-verified, and an incomplete download is deleted.
5. Review `impdp_full.par` and target readiness. `export DP_IMPORT_CONNECT='/@DPTARGET'; export PHCAFE_APPROVE_IMPORT=YES; ./run_import.sh` (or run `impdp /@DPTARGET parfile=impdp_full.par` manually).
6. Review Data Pump import log for object failures, compare `sql/04_target_validation.sql` against saved source inventory, check INPLAY procedures, packages, views, synonyms, grants and representative actual COUNT(*) and business totals. Test application logon and controlled shutdown/restart. Imported target is independent of missing source redo.
7. Only after successful independent import, validation and restart call this baseline `LOGICAL DR IMPORT VERIFIED`. Transfer checksums alone merit only `TRANSFER VERIFIED`.

## Useful checks and notifications

`python3 dr_manager.py --config config.json --test-s3`

`python3 dr_manager.py --config config.json --upload`

`python3 dr_manager.py --config config.json --download`

`python3 dr_manager.py --config config.json --alert 'manual alert test'`

An email failure will be logged and not be represented as successful delivery. Python cannot email after a host crash or kill -9; use a separate external heartbeat monitor. `run_export.sh`/`run_import.sh` install error traps to notify on command errors; Ctrl+C/process death requires independent monitoring.

## Speed

The allocated size (~599 GiB) is not the amount exported. Measure `DBA_SEGMENTS` and a small test export. As a rough illustration, **300 GiB of actual dump data** takes ~2.8 hours at sustained 30 MiB/s or ~57 minutes at sustained 90 MiB/s, before S3 upload and full readback verification. Export speed depends on the original Oracle instance's reads/CPU, staging I/O and network, LOB types, and export degree. `PARALLEL=2` is conservative for your only surviving database. Increase only after monitoring its health. The kit deliberately uses a full S3 readback checksum, so uploading adds network I/O and time, but provides a stronger end-to-end check.

## Source safety

Run SQL file 01 only on PHCAFE. Never run file 02, 03, full import or `RESETLOGS` against the source. Data Pump `NETWORK_LINK` reads source; it requires a writable **staging** database for the job and master table. If `expdp` fails, the source can remain intact; investigate without rebooting it.
