#!/usr/bin/env python3
"""Воспроизводимый архив в памяти; публичный тестовый ключ не является ключом выпуска."""
import copy
import io
from pathlib import Path
import sys
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import release_archive_study as archive
import release_policy_study as policy
import test_release_policy_study as fixtures

class ReleaseArchiveStudyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReleasePolicyStudyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.statement=policy.canonical(self.f.doc);self.sig=self.f.sign()
        self.raw=archive.build(self.f.manifest,self.f.files)
    def assess(self,raw=None,statement=None,signature=None,trust=None):
        return archive.assess(self.raw if raw is None else raw,self.statement if statement is None else statement,
                    self.sig if signature is None else signature,policy=self.f.policy if trust is None else trust,
                    verify_signature=self.f.fx.verify)
    def error(self,code,**kw):
        with self.assertRaises(archive.ArchiveError) as e:self.assess(**kw)
        self.assertEqual(str(e.exception),code)
    def repack(self,transform):
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.raw)) as source,zipfile.ZipFile(out,'w') as dest:
            for info in source.infolist():
                content=source.read(info);name=info.filename
                replacement=transform(name,content,info)
                if replacement is None:continue
                newname,newcontent,newinfo=replacement
                newinfo.filename=newname;dest.writestr(newinfo,newcontent)
        return out.getvalue()
    def test_reproducible_and_signed_full_archive(self):
        self.assertEqual(self.raw,archive.build(self.f.manifest,dict(reversed(list(self.f.files.items())))))
        result=self.assess();self.assertEqual(result['outcome'],'study_policy_consistent')
        self.assertEqual(result['extraction'],'not_performed');self.assertEqual(result['freshness'],'not_proved')
    def test_foreign_wrong_signature_revoked_and_rollback(self):
        self.error('policy_refused:signature_invalid',signature=bytes(64))
        p=copy.deepcopy(self.f.policy);p['revoked']=[self.f.key_id];self.error('policy_refused:key_untrusted_or_revoked',trust=p)
        p=copy.deepcopy(self.f.policy);p['checkpoint']={'sequence':4,'statement_sha256':'0'*64};self.error('policy_refused:rollback_refused',trust=p)
    def test_changed_missing_extra_and_noncanonical_bytes(self):
        altered=dict(self.f.files);altered['kit/verify_candidate.py']+=b'\n# tamper\n'
        self.error('policy_refused:files_mismatch',raw=archive.build(self.f.manifest,altered))
        altered=dict(self.f.files);del altered['kit/verify_candidate.py']
        self.error('policy_refused:manifest_invalid',raw=archive.build(self.f.manifest,altered))
        altered=dict(self.f.files);altered['kit/extra.py']=b'extra'
        self.error('policy_refused:manifest_invalid',raw=archive.build(self.f.manifest,altered))
        self.error('archive_noncanonical',raw=self.raw+b'extra')
    def test_path_symlink_compression_and_zip_duplicate_rejected(self):
        target='kit/verify_candidate.py'
        def invalid_name(name,data,info):return ('../escape' if name==target else name,data,info)
        self.error('archive_members_invalid',raw=self.repack(invalid_name))
        def symlink(name,data,info):
            if name==target:info.external_attr=0o120777<<16
            return name,data,info
        self.error('archive_members_invalid',raw=self.repack(symlink))
        def compressed(name,data,info):
            if name==target:info.compress_type=zipfile.ZIP_DEFLATED
            return name,data,info
        self.error('archive_members_invalid',raw=self.repack(compressed))
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('kit/KIT-VERSION.json',b'one')
            z.writestr('kit/a',b'two');z.writestr('kit/a',b'three')
        self.error('archive_members_invalid',raw=out.getvalue())
    def test_invalid_or_unbounded_input_and_no_path_traversal(self):
        self.error('archive_invalid',raw=b'not a zip')
        self.error('archive_invalid',raw=b'x'*(archive.MAX_ARCHIVE+1))
        for bad in ('../x','kit/../x','kit/sub/a','kit\\evil'):
            with self.subTest(bad=bad):
                with self.assertRaises(archive.ArchiveError):archive.build(self.f.manifest,{bad:b'data'})

if __name__=='__main__':unittest.main()
