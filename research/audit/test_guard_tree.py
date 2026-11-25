#!/usr/bin/env python3
"""Guard Git tree только на синтетических временных репозиториях без коммитов."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.guard_tree import MAX_BLOB, TreeViolation, guard_commit, guard_tree


class GuardTreeTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('git'):
            self.skipTest('Git недоступен')
        self.temp = tempfile.TemporaryDirectory(prefix='kit-tree-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root/'repo'; self.repo.mkdir()
        self.env = {'PATH': os.defpath, 'LC_ALL':'C', 'GIT_CONFIG_NOSYSTEM':'1',
                    'GIT_CONFIG_GLOBAL':os.devnull, 'GIT_ALLOW_PROTOCOL':'', 'GIT_TERMINAL_PROMPT':'0'}
        for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP'):
            if key in os.environ: self.env[key] = os.environ[key]
        self.git('init', '-q', '--template=')
        manifest = ROOT/'kit/KIT-VERSION.json'
        self.doc = json.loads(manifest.read_text(encoding='utf-8'))
        self.paths = ['kit/KIT-VERSION.json', *self.doc['files']]
        for name in self.paths:
            target = self.repo/name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, target)
        self.git('-c', 'core.autocrlf=false', 'add', '--', *self.paths)
        self.tree = self.git('write-tree').strip()
        self.pin = hashlib.sha256(manifest.read_bytes()).hexdigest()

    def git(self, *args, input=None):
        p = subprocess.run(['git','-C',str(self.repo),*args],env=self.env,input=input,
                           capture_output=True,timeout=30)
        if p.returncode: raise AssertionError((args, p.stderr.decode(errors='replace')))
        return p.stdout.decode('ascii')

    def check(self, tree=None, pin=None):
        return guard_tree(self.repo, tree_oid=self.tree if tree is None else tree,
                          manifest_pin=self.pin if pin is None else pin)

    def violation(self, reason, tree=None, pin=None):
        with self.assertRaises(TreeViolation) as exc: self.check(tree, pin)
        self.assertEqual(exc.exception.reason, reason)

    def test_pinned_tree_pass_and_no_index_change(self):
        before = self.git('status','--porcelain=v1','-z')
        report = self.check()
        self.assertEqual(report['outcome'],'pass')
        self.assertEqual(report['tree_oid'],self.tree)
        self.assertEqual(report['manifest_sha256'],self.pin)
        self.assertEqual(report['files'],len(self.doc['files']))
        self.assertEqual(report['checked'],'candidate_l0_only')
        self.assertEqual(before,self.git('status','--porcelain=v1','-z'))
        self.assertEqual(self.tree,self.git('write-tree').strip())

    def test_working_tree_not_checked_and_staged_changes_are_detected(self):
        path = self.repo/'kit/base/SCHEMA-V2.md'; path.write_bytes(path.read_bytes()+b'changed')
        self.assertEqual(self.check()['outcome'],'pass')
        self.git('add','--','kit/base/SCHEMA-V2.md')
        changed = self.git('write-tree').strip()
        self.assertNotEqual(changed,self.tree)
        self.violation('candidate_digest_mismatch',tree=changed)
        self.assertEqual(self.check()['outcome'],'pass')

    def test_modified_manifest_cannot_follow_changes_without_trusted_pin(self):
        path = self.repo/'kit/base/SCHEMA-V2.md'; path.write_bytes(path.read_bytes()+b'changed')
        self.doc['files']['kit/base/SCHEMA-V2.md']=hashlib.sha256(path.read_bytes()).hexdigest()
        (self.repo/'kit/KIT-VERSION.json').write_text(json.dumps(self.doc,sort_keys=True),encoding='utf-8')
        self.git('add','--','kit/base/SCHEMA-V2.md','kit/KIT-VERSION.json')
        self.violation('manifest_pin_mismatch',tree=self.git('write-tree').strip())

    def test_extra_or_missing_base_file(self):
        path = self.repo/'kit/base/extra.py'; path.write_text('not executed',encoding='utf-8')
        self.git('add','--','kit/base/extra.py')
        self.violation('candidate_members_mismatch',tree=self.git('write-tree').strip())
        self.git('update-index','--force-remove','--','kit/base/extra.py','kit/base/SCHEMA-V2.md')
        self.violation('candidate_members_mismatch',tree=self.git('write-tree').strip())

    def test_nested_base_file_rejected(self):
        path = self.repo/'kit/base/nested/unexpected'; path.parent.mkdir(); path.write_text('not read',encoding='utf-8')
        self.git('add','--','kit/base/nested/unexpected')
        self.violation('tree_entry_invalid',tree=self.git('write-tree').strip())

    def test_executable_mode_rejected_even_with_identical_bytes(self):
        self.git('update-index','--chmod=+x','--','kit/base/SCHEMA-V2.md')
        self.violation('tree_entry_invalid',tree=self.git('write-tree').strip())

    def test_symlink_blob_rejected(self):
        path = self.repo/'kit/base/SCHEMA-V2.md'; path.unlink()
        try: path.symlink_to('STORAGE-V2.md')
        except OSError as exc: self.skipTest(f'нет символических ссылок: {exc}')
        self.git('add','--','kit/base/SCHEMA-V2.md')
        self.violation('tree_entry_invalid',tree=self.git('write-tree').strip())

    def test_wrong_object_and_bad_ids(self):
        blob = self.git('hash-object','-w','--stdin',input=b'synthetic').strip()
        self.violation('tree_invalid',tree=blob)
        for tree in ('HEAD','--help','0'*39,'A'*40,''):
            with self.subTest(tree=tree): self.violation('tree_invalid',tree=tree)
        self.violation('git_failed',tree='0'*40)

    def test_pin_required_before_git(self):
        for pin in (None,'','A'*64,'0'*63,1):
            with self.subTest(pin=pin), patch('kit.guard_tree._Git') as git:
                with self.assertRaises(TreeViolation) as exc:
                    guard_tree(self.repo,tree_oid=self.tree,manifest_pin=pin)
                self.assertEqual(exc.exception.reason,'pin_required')
                git.assert_not_called()
        self.violation('manifest_pin_mismatch',pin='0'*64)

    def test_corrupt_manifest_rejected_even_if_given_its_hash(self):
        path = self.repo/'kit/KIT-VERSION.json'; path.write_bytes(b'{"format":1,"format":1}')
        self.git('add','--','kit/KIT-VERSION.json')
        self.violation('manifest_invalid',tree=self.git('write-tree').strip(),pin=hashlib.sha256(path.read_bytes()).hexdigest())

    def test_oversized_blob_is_refused(self):
        path = self.repo/'kit/base/SCHEMA-V2.md'; path.write_bytes(b'x'*(MAX_BLOB+1))
        self.git('add','--','kit/base/SCHEMA-V2.md')
        self.violation('blob_too_large',tree=self.git('write-tree').strip())

    def test_inherited_git_environment_is_not_used(self):
        with patch.dict(os.environ, {'GIT_DIR':str(self.root/'nonexistent'),
                                     'GIT_INDEX_FILE':str(self.root/'bad-index'),
                                     'GIT_CONFIG_GLOBAL':str(self.root/'bad-config')}):
            self.assertEqual(self.check()['outcome'],'pass')

    def test_target_verifier_is_never_imported(self):
        marker = self.root/'executed'
        (self.repo/'kit/verify_candidate.py').write_text(
            'from pathlib import Path\nPath('+repr(str(marker))+').write_text("bad")\n', encoding='utf-8')
        self.git('add','--','kit/verify_candidate.py')
        p = self.cli(self.git('write-tree').strip())
        self.assertEqual(p.returncode,1,p.stderr)
        self.assertEqual(json.loads(p.stdout)['reason'],'candidate_digest_mismatch')
        self.assertFalse(marker.exists())

    def test_malicious_tree_guard_is_not_executed(self):
        (self.repo/'kit/guard_tree.py').write_text('raise SystemExit(0)\n',encoding='utf-8')
        self.git('add','--','kit/guard_tree.py')
        tree = self.git('write-tree').strip()
        p = self.cli(tree)
        self.assertEqual(p.returncode,1,p.stderr)
        self.assertEqual(json.loads(p.stdout)['reason'],'candidate_digest_mismatch')

    def cli(self, tree):
        return subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/guard_tree.py'),
                               '--repo',str(self.repo),'--tree',tree,'--manifest-pin',self.pin],
                              cwd=self.repo,env=self.env,capture_output=True,text=True,encoding='utf-8',timeout=60)

    def test_isolated_cli_success(self):
        p = self.cli(self.tree)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['tree_oid'],self.tree)

    def commit(self, tree, message='synthetic'):
        # Создаёт только объект commit в синтетическом репозитории, без веток и ссылок.
        return self.git('-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid',
                        'commit-tree',tree,'-m',message).strip()

    def test_commit_binds_exact_object_to_checked_tree(self):
        commit = self.commit(self.tree)
        result = guard_commit(self.repo,commit_oid=commit,manifest_pin=self.pin)
        self.assertEqual(result['outcome'],'pass')
        self.assertEqual(result['commit_oid'],commit)
        self.assertEqual(result['tree_oid'],self.tree)
        self.assertEqual(result['guard_commit_format'],1)
        self.assertNotIn('guard_tree_format',result)
        self.assertEqual(self.git('write-tree').strip(),self.tree)
        p = subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/guard_tree.py'),
                            '--repo',str(self.repo),'--commit',commit,'--manifest-pin',self.pin],
                           cwd=self.repo,env=self.env,capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['commit_oid'],commit)

    def test_commit_rejects_bad_oid_and_wrong_object_type(self):
        for oid in ('HEAD','--help','0'*39,'A'*40,'',self.tree):
            with self.subTest(oid=oid), self.assertRaises(TreeViolation) as exc:
                guard_commit(self.repo,commit_oid=oid,manifest_pin=self.pin)
            self.assertEqual(exc.exception.reason,'commit_invalid')
        with self.assertRaises(TreeViolation) as exc:
            guard_commit(self.repo,commit_oid='0'*40,manifest_pin=self.pin)
        self.assertEqual(exc.exception.reason,'git_failed')
        with patch('kit.guard_tree._Git') as git:
            with self.assertRaises(TreeViolation) as exc:
                guard_commit(self.repo,commit_oid='0'*40,manifest_pin=None)
            self.assertEqual(exc.exception.reason,'pin_required')
            git.assert_not_called()

    def test_commit_with_modified_candidate_fails(self):
        path = self.repo/'kit/base/SCHEMA-V2.md'; path.write_bytes(path.read_bytes()+b'changed')
        self.git('add','--','kit/base/SCHEMA-V2.md')
        commit = self.commit(self.git('write-tree').strip())
        with self.assertRaises(TreeViolation) as exc:
            guard_commit(self.repo,commit_oid=commit,manifest_pin=self.pin)
        self.assertEqual(exc.exception.reason,'candidate_digest_mismatch')
        p = subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/guard_tree.py'),
                            '--repo',str(self.repo),'--commit',commit,'--manifest-pin',self.pin],
                           cwd=self.repo,env=self.env,capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(p.returncode,1)
        self.assertEqual(json.loads(p.stdout), {'guard_commit_format':1, 'outcome':'violation',
                                               'reason':'candidate_digest_mismatch'})

    def test_git_replace_cannot_redirect_checked_commit(self):
        original = self.commit(self.tree, 'original')
        path = self.repo/'kit/base/SCHEMA-V2.md'; path.write_bytes(path.read_bytes()+b'changed')
        self.git('add','--','kit/base/SCHEMA-V2.md')
        bad_tree = self.git('write-tree').strip(); replacement = self.commit(bad_tree, 'replacement')
        # replace только в этом временном репозитории, не в рабочей истории проекта.
        self.git('replace',original,replacement)
        self.assertIn('tree '+bad_tree, self.git('cat-file','-p',original))
        result = guard_commit(self.repo,commit_oid=original,manifest_pin=self.pin)
        self.assertEqual(result['tree_oid'],self.tree)
        self.assertEqual(result['commit_oid'],original)
        with self.assertRaises(TreeViolation) as exc:
            guard_commit(self.repo,commit_oid=replacement,manifest_pin=self.pin)
        self.assertEqual(exc.exception.reason,'candidate_digest_mismatch')

    def test_malformed_commit_tree_lookup_fails_closed(self):
        with patch('kit.guard_tree._Git') as factory:
            fake = factory.return_value; fake.oid_length=40
            fake.run.side_effect=[b'commit\\n',b'not-a-tree\\n']
            with self.assertRaises(TreeViolation) as exc:
                guard_commit(self.repo,commit_oid='a'*40,manifest_pin=self.pin)
            self.assertEqual(exc.exception.reason,'commit_invalid')

    def test_cli_rejects_both_commit_and_tree(self):
        commit = self.commit(self.tree)
        p = subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/guard_tree.py'),
                            '--repo',str(self.repo),'--commit',commit,'--tree',self.tree,
                            '--manifest-pin',self.pin],cwd=self.repo,env=self.env,
                           capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(p.stdout)

    def test_subdirectory_is_not_accepted_as_repository_root(self):
        with self.assertRaises(TreeViolation) as exc:
            guard_tree(self.repo/'kit',tree_oid=self.tree,manifest_pin=self.pin)
        self.assertEqual(exc.exception.reason,'repository_invalid')

    def test_sha256_git_tree_when_supported(self):
        other=self.root/'sha256'; other.mkdir()
        p=subprocess.run(['git','-C',str(other),'init','-q','--template=','--object-format=sha256'],
                         env=self.env,capture_output=True,timeout=30)
        if p.returncode: self.skipTest('Git без поддержки sha256')
        for name in self.paths:
            target=other/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,target)
        subprocess.run(['git','-C',str(other),'-c','core.autocrlf=false','add','--',*self.paths],env=self.env,check=True,capture_output=True)
        tree=subprocess.check_output(['git','-C',str(other),'write-tree'],env=self.env).decode().strip()
        report=guard_tree(other,tree_oid=tree,manifest_pin=self.pin)
        self.assertEqual(len(tree),64)
        self.assertEqual(report['git_object_format'],'sha256')
        self.assertEqual(report['outcome'],'pass')
        commit=subprocess.check_output(['git','-C',str(other),'-c','user.name=Synthetic',
                                        '-c','user.email=synthetic@example.invalid','commit-tree',tree,'-m','synthetic'],
                                       env=self.env).decode().strip()
        result=guard_commit(other,commit_oid=commit,manifest_pin=self.pin)
        self.assertEqual((result['commit_oid'],result['tree_oid']), (commit,tree))


if __name__ == '__main__': unittest.main()
