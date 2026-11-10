#!/usr/bin/env python3
"""PHCAFE Data Pump: verify S3, transfer completed dump pieces, fetch/verify for import, SMTP notify.
No access to or modification of PHCAFE source Oracle database. Python 3.9+ / boto3.
"""
import argparse
import hashlib
import json
import os
import socket
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from mailer import Mailer


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def loadcfg(filename):
    cfg = json.loads(Path(filename).read_text())
    for key in ('bucket', 'region', 'prefix', 'dump_dir', 'log_dir'):
        if not cfg.get(key):
            raise ValueError(f'Missing {key} in config')
    cfg['prefix'] = cfg['prefix'].strip('/')
    return cfg


def notify(cfg, status, msg, attachments=None):
    settings = cfg.get('email', {})
    try:
        pwd_path = settings.get('password_file')
        pwd = Path(pwd_path).read_text().strip() if settings.get('enabled') and pwd_path else None
        mailer = Mailer(enabled=settings.get('enabled', False),
                        smtp_host=settings.get('smtp_host', 'localhost'),
                        smtp_port=settings.get('smtp_port', 25),
                        sender=settings.get('sender', 'oracle@localhost'),
                        recipients=settings.get('recipients', []),
                        username=settings.get('username'), password=pwd,
                        use_tls=settings.get('use_tls', False))
        mailer.send(f'[PHCAFE DATAPUMP DR] {status}',
                    f'Time UTC: {utcnow()}\nHost: {socket.gethostname()}\n\n{msg}',
                    attachments=attachments)
    except Exception as exc:
        print(f'WARNING: notification failed: {type(exc).__name__}: {exc}', file=sys.stderr)


def sha256(path):
    dig = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            dig.update(block)
    return dig.hexdigest()


def sha256_s3(s3, bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    dig = hashlib.sha256()
    size = 0
    try:
        for part in response['Body'].iter_chunks(chunk_size=8 * 1024 * 1024):
            if part:
                dig.update(part)
                size += len(part)
    finally:
        response['Body'].close()
    return dig.hexdigest(), size


def s3_client(cfg):
    return boto3.client('s3', region_name=cfg['region'])


def log(cfg, msg):
    line = f'{utcnow()} {msg}'
    print(line, flush=True)
    outdir = Path(cfg['log_dir'])
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / 'dr_manager.log').open('a') as handle:
        handle.write(line + '\n')


def test_s3(cfg):
    import uuid
    s3 = s3_client(cfg)
    s3.head_bucket(Bucket=cfg['bucket'])
    s3.list_objects_v2(Bucket=cfg['bucket'], Prefix=cfg['prefix'] + '/', MaxKeys=1)
    key = cfg['prefix'] + '/_connectivity_test/' + str(uuid.uuid4()) + '.txt'
    body = os.urandom(1024 * 1024)
    digest = hashlib.sha256(body).hexdigest()
    s3.put_object(Bucket=cfg['bucket'], Key=key, Body=body,
                  Metadata={'sha256': digest})
    data = s3.get_object(Bucket=cfg['bucket'], Key=key)['Body'].read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError('TEST S3: checksum failed')
    log(cfg, f'TEST S3 PASS: read/write/integrity; harmless test key retained: s3://{cfg["bucket"]}/{key}')


def dump_files(cfg):
    directory = Path(cfg['dump_dir'])
    if not directory.is_dir():
        raise RuntimeError(f'Dump directory missing: {directory}')
    files = sorted(directory.glob('PHCAFE_FULL_*.dmp'))
    if not files:
        raise RuntimeError('No PHCAFE_FULL_*.dmp files in dump directory')
    export_log = directory / 'PHCAFE_FULL_EXPORT.log'
    if not export_log.exists():
        raise RuntimeError('Required Data Pump export log missing')
    content = export_log.read_text(errors='replace')
    if 'successfully completed' not in content.lower():
        raise RuntimeError('Export log does not show successfully completed; do not upload as complete')
    # Fail closed on Oracle Data Pump log that contains an error identifier even if summary reports success.
    import re
    hits = sorted(set(re.findall(r'\bORA-\d{5}\b|\bUDE-\d{5}\b', content)))
    if hits:
        raise RuntimeError('Export log contains Oracle error codes: ' + ', '.join(hits) + '; investigate before approval')
    return files, export_log


def manifest_path(cfg):
    return Path(cfg['dump_dir']) / 'PHCAFE_FULL_MANIFEST.json'


def upload(cfg):
    s3 = s3_client(cfg)
    files, exp_log = dump_files(cfg)
    parts = []
    transfer = TransferConfig(multipart_threshold=64 * 1024 * 1024,
                              multipart_chunksize=64 * 1024 * 1024,
                              max_concurrency=2, use_threads=True)
    for file in files:
        size = file.stat().st_size
        checksum = sha256(file)
        key = f'{cfg["prefix"]}/dumps/{file.name}'
        log(cfg, f'UPLOAD START {file.name} bytes={size} sha256={checksum}')
        existing = None
        try:
            existing = s3.head_object(Bucket=cfg['bucket'], Key=key)
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') not in ('404', 'NoSuchKey', 'NotFound'):
                raise
        if existing:
            if existing['ContentLength'] != size or existing.get('Metadata', {}).get('sha256') != checksum:
                raise RuntimeError(f'CONFLICT: existing S3 object differs; refusing overwrite: {key}')
            log(cfg, f'EXISTING OBJECT MATCHES METADATA; will verify full bytes: {file.name}')
        else:
            s3.upload_file(str(file), cfg['bucket'], key,
                           ExtraArgs={'Metadata': {'sha256': checksum}}, Config=transfer)
        # End-to-end GET verification, not merely self-declared HEAD metadata.
        remote_checksum, remote_size = sha256_s3(s3, cfg['bucket'], key)
        if remote_size != size or remote_checksum != checksum:
            raise RuntimeError(f'S3 READBACK SHA256 MISMATCH: {key} local={checksum} remote={remote_checksum}')
        if sha256(file) != checksum or file.stat().st_size != size:
            raise RuntimeError(f'LOCAL DUMP CHANGED DURING TRANSFER: {file.name}')
        parts.append({'name': file.name, 'bytes': size, 'sha256': checksum, 'key': key})
        log(cfg, f'UPLOAD VERIFIED {file.name} bytes={size} sha256={checksum}')
    man = {'format': 1, 'created_utc': utcnow(), 'bucket': cfg['bucket'],
           'region': cfg['region'], 'prefix': cfg['prefix'], 'files': parts,
           'status': 'TRANSFER_VERIFIED_NOT_IMPORT_TESTED'}
    mp = manifest_path(cfg)
    mp.write_text(json.dumps(man, indent=2) + '\n')
    for local, name in [(exp_log, exp_log.name), (mp, mp.name)]:
        s3.upload_file(str(local), cfg['bucket'], f'{cfg["prefix"]}/metadata/{name}')
    log(cfg, f'TRANSFER VERIFIED: {len(parts)} dump pieces; NOT YET IMPORT VERIFIED')
    notify(cfg, 'TRANSFER VERIFIED', f'{len(parts)} Data Pump pieces uploaded and byte-verified. Import test still required.', [str(mp)])


def fetch(cfg):
    s3 = s3_client(cfg)
    key = f'{cfg["prefix"]}/metadata/PHCAFE_FULL_MANIFEST.json'
    manifest = json.loads(s3.get_object(Bucket=cfg['bucket'], Key=key)['Body'].read())
    if manifest.get('status') != 'TRANSFER_VERIFIED_NOT_IMPORT_TESTED' or manifest.get('bucket') != cfg['bucket'] or manifest.get('prefix') != cfg['prefix']:
        raise RuntimeError('Manifest does not describe verified backup for configured S3 prefix')
    dest = Path(cfg['dump_dir'])
    dest.mkdir(parents=True, exist_ok=True)
    for entry in manifest['files']:
        name = entry['name']
        if Path(name).name != name or not name.startswith('PHCAFE_FULL_') or not name.endswith('.dmp'):
            raise RuntimeError('Unsafe dump filename in remote manifest')
        target = dest / name
        if target.exists():
            if target.stat().st_size == entry['bytes'] and sha256(target) == entry['sha256']:
                log(cfg, f'RESTORE SKIP verified existing {name}')
                continue
            raise RuntimeError(f'Restored destination exists and differs: {target}')
        partial = dest / (name + '.download_partial')
        try:
            if partial.exists():
                partial.unlink()
            s3.download_file(cfg['bucket'], entry['key'], str(partial))
            if partial.stat().st_size != entry['bytes'] or sha256(partial) != entry['sha256']:
                raise RuntimeError(f'DOWNLOAD SHA256 FAILED {name}')
            partial.replace(target)
            log(cfg, f'RESTORE VERIFIED {name}')
        finally:
            if partial.exists():
                partial.unlink()
    log(cfg, 'ALL DUMP FILES RESTORED AND SHA256 VERIFIED; impdp STILL REQUIRED')
    notify(cfg, 'DUMPS DOWNLOADED', 'All Data Pump dumps verified locally. Oracle impdp has not yet been run.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--test-s3', action='store_true')
    group.add_argument('--upload', action='store_true')
    group.add_argument('--download', action='store_true')
    group.add_argument('--alert', metavar='MESSAGE')
    args = ap.parse_args()
    cfg = loadcfg(args.config)
    try:
        if args.test_s3: test_s3(cfg)
        elif args.upload: upload(cfg)
        elif args.download: fetch(cfg)
        elif args.alert:
            log(cfg, 'ALERT: ' + args.alert)
            notify(cfg, 'JOB FAILED / STOPPED', args.alert, [str(Path(cfg['log_dir']) / 'dr_manager.log')])
    except BaseException as exc:
        detail = f'{type(exc).__name__}: {exc}\n\n' + traceback.format_exc()
        log(cfg, 'FAILED: ' + detail)
        log_file = str(Path(cfg['log_dir']) / 'dr_manager.log')
        # Keep attachment small to avoid Gmail size limits and accidental leakage.
        report = Path(cfg['log_dir']) / f'failure_{int(time.time())}.txt'
        report.write_text(detail[-120000:])
        notify(cfg, 'FAILED / STOPPED', detail[-10000:], [str(report)])
        raise SystemExit(1)

if __name__ == '__main__':
    main()
