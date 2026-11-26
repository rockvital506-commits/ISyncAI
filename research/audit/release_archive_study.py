#!/usr/bin/env python3
"""Канонический архив в памяти поверх .74: эксперимент, не установщик."""
import io
import zipfile
import release_policy_study as policy_study

MAX_ARCHIVE = 20 * 1024 * 1024
MANIFEST = 'kit/KIT-VERSION.json'


class ArchiveError(ValueError):
    pass


def build(manifest, files):
    """Построение не подписывает и не подтверждает доверие/корректность содержимого."""
    if (type(manifest) is not bytes or not 0 < len(manifest) <= policy_study.MAX_DOCUMENT or
            type(files) is not dict or not 1 <= len(files) <= policy_study.MAX_FILES or MANIFEST in files or
            any(not policy_study._path(name) or type(data) is not bytes or len(data)>policy_study.MAX_DOCUMENT
                for name,data in files.items()) or sum(map(len,files.values()))+len(manifest)>policy_study.MAX_TOTAL):
        raise ArchiveError('inputs_invalid')
    members = dict(files); members[MANIFEST] = manifest
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    result = target.getvalue()
    if len(result)>MAX_ARCHIVE: raise ArchiveError('archive_too_large')
    return result


def assess(archive_bytes, statement, signature, *, policy, verify_signature):
    """Оценивает только bytes в памяти, внешний policy/callback и подпись .74."""
    if type(archive_bytes) is not bytes or not 0 < len(archive_bytes) <= MAX_ARCHIVE:
        raise ArchiveError('archive_invalid')
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), 'r') as archive:
            rows=archive.infolist()
            names=[row.filename for row in rows]
            if (not 2 <= len(rows) <= policy_study.MAX_FILES+1 or len(set(names))!=len(names) or
                    MANIFEST not in names or any(name != MANIFEST and not policy_study._path(name) for name in names) or
                    any(row.is_dir() or row.compress_type != zipfile.ZIP_STORED or row.flag_bits & 1 or
                        row.file_size > policy_study.MAX_DOCUMENT or row.compress_size != row.file_size or
                        (row.external_attr >> 16) != 0o100600 for row in rows) or
                    sum(row.file_size for row in rows)>policy_study.MAX_TOTAL):
                raise ArchiveError('archive_members_invalid')
            data={row.filename:archive.read(row) for row in rows}
        manifest=data.pop(MANIFEST)
        if build(manifest,data)!=archive_bytes: raise ArchiveError('archive_noncanonical')
        result=policy_study.assess(statement,signature,policy=policy,files=data,manifest=manifest,verify_signature=verify_signature)
        return dict(result,archive='canonical_in_memory',extraction='not_performed',
                    filesystem_types_and_races='not_checked',checker_origin='assumed_not_verified')
    except ArchiveError: raise
    except policy_study.PolicyError as error: raise ArchiveError('policy_refused:'+str(error)) from error
    except (zipfile.BadZipFile,zipfile.LargeZipFile,OSError,RuntimeError,ValueError,TypeError,KeyError,NotImplementedError,OverflowError) as error:
        raise ArchiveError('archive_invalid') from error
