#!/usr/bin/env python3
"""Структурный preflight обновления; не обновление Kit и не N−1."""
import hashlib

from kit.base import registry_store
from kit.verify_candidate import CANDIDATE_VERSION
import registry_backup_study as backup
import release_archive_study as archive


class UpdateError(ValueError):pass


def assess(layout,*,old_system_pin,archive_bytes,statement,signature,policy,verify_signature):
    """Только наблюдение: подпись и pin предполагают доверенные внешние источники."""
    if not isinstance(layout,registry_store.Layout):raise UpdateError('layout_invalid')
    try:
        archive_report,rows=archive.capture(archive_bytes,statement,signature,policy=policy,
                                            verify_signature=verify_signature)
        wire,old_report=backup.capture(layout,system_pin=old_system_pin)
        _,old=backup.inspect(wire,system_pin=old_system_pin)
        files=dict(rows);new_l0=files['kit/SYSTEM-L0.json'];new_pin=hashlib.sha256(new_l0).hexdigest()
        new_data={'L0':new_l0,'L1':old['L1'],'L2':old['L2']}
        docs=backup._check_data(layout.profile_root,new_pin,new_data)
        if docs['L0']['release_version']!=CANDIDATE_VERSION:
            raise UpdateError('candidate_version_unsupported')
        return {'outcome':'structural_preflight_only','profile_root':layout.profile_root,
                'old_system_sha256':old_system_pin,'candidate_system_sha256':new_pin,
                'system_changed':old['L0']!=new_l0,
                'l1_sha256':hashlib.sha256(old['L1']).hexdigest(),
                'l2_sha256':hashlib.sha256(old['L2']).hexdigest(),
                'candidate_statement_sha256':archive_report['statement_sha256'],
                'source_snapshot_sha256':old_report['file_sha256'],
                'schema':'pretrusted_current_v2_only','code_compatibility':'not_checked',
                'semantics':'not_checked','authorization':'not_checked','origin':'assumed_not_verified',
                'concurrency':'cooperative_snapshot_only','checkpoint':'not_updated',
                'update':'not_performed','rollback':'not_performed'}
    except UpdateError:raise
    except archive.ArchiveError as error:raise UpdateError('archive_unverified') from error
    except backup.BackupError as error:raise UpdateError('workspace_or_catalog_invalid') from error
    except (KeyError,TypeError,ValueError,RecursionError) as error:raise UpdateError('preflight_invalid') from error
