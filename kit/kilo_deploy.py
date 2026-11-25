#!/usr/bin/env python3
"""Контролируемое создание одного производного файла Kilo по подтверждённому плану."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from secrets import token_hex

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import registry_store, schema_v2
from kit.base.profile_journal import canonical_bytes
from kit.base.registry_store import Layout, StoreError
from kit.render_rule import RenderError, render


class DeployError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _dirs(loaded):
    # Область среды не может быть корнем или содержимым любого из трёх корней реестров.
    dest = ('.kilo', 'rules')
    for root in loaded.roots.values():
        parts = tuple(part.casefold() for part in root.split('/'))
        if parts[:len(dest)] == dest or dest[:len(parts)] == parts:
            raise DeployError('root_overlap')
    path, info = registry_store._existing(loaded.workspace, '.kilo/rules')
    for area_root in loaded.roots.values():
        _, st = registry_store._existing(loaded.workspace, area_root)
        if (st.st_dev, st.st_ino) == (info.st_dev, info.st_ino):
            raise DeployError('root_overlap')
    return path, (info.st_dev, info.st_ino)


def _target_absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise DeployError('target_unreadable') from exc
    raise DeployError('target_exists')


def _stage_stat(path, identity):
    try:
        info = path.lstat()
    except OSError as exc:
        raise DeployError('cleanup_unsafe') from exc
    if (not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & registry_store._REPARSE
            or (info.st_dev, info.st_ino) != identity):
        raise DeployError('cleanup_unsafe')
    return info


def _remove_stage(path, identity):
    # При неопределённой идентичности не удалять чужой объект.
    _stage_stat(path, identity)
    try:
        path.unlink()
    except OSError as exc:
        raise DeployError('cleanup_failed') from exc


class KiloDeploymentSession:
    """Единственный ожидающий план, данные принимаются в пределах доверенного Layout."""

    def __init__(self, layout):
        self.layout = layout
        self._pending = None

    def cancel(self):
        self._pending = None

    def plan(self, *, area, entry_id):
        self.cancel()
        loaded = registry_store._load(self.layout)
        content = render(loaded.documents, area=area, entry_id=entry_id)
        directory, identity = _dirs(loaded)
        # render уже проверил ID схемой, поэтому имя не может содержать разделители пути.
        name = f'kit-{area.lower()}-{entry_id}.md'
        _target_absent(directory / name)
        ticket = token_hex(32)
        result = {'plan_format': 2, 'outcome': 'planned', 'target': '.kilo/rules/' + name,
                  'area': area, 'entry_id': entry_id, 'inputs_sha256': dict(loaded.inputs_sha256),
                  'content_sha256': hashlib.sha256(content).hexdigest(),
                  'content': content.decode('utf-8'), 'ticket': ticket,
                  'staging_target': '.kilo/rules/.kit-stage-' + ticket + '.tmp'}
        self._pending = (canonical_bytes(result), ticket, content, identity)
        return result

    def apply(self, plan, *, confirmed_ticket=None):
        if type(confirmed_ticket) is not str or not confirmed_ticket or type(plan) is not dict or plan.get('ticket') != confirmed_ticket:
            raise DeployError('confirmation_required')
        pending = self._pending
        if pending is None or pending[1] != confirmed_ticket:
            raise DeployError('ticket_unknown')
        try:
            if canonical_bytes(plan) != pending[0]:
                raise DeployError('plan_mismatch')
        except (TypeError, ValueError, UnicodeError) as exc:
            if isinstance(exc, DeployError):
                raise
            raise DeployError('plan_mismatch') from exc
        self.cancel()  # Один точный билет — одна попытка, даже если проверка или запись отказали.
        loaded = registry_store._load(self.layout)
        directory, identity = _dirs(loaded)
        if identity != pending[3] or loaded.inputs_sha256 != plan['inputs_sha256']:
            raise DeployError('stale_plan')
        content = render(loaded.documents, area=plan['area'], entry_id=plan['entry_id'])
        if content != pending[2] or hashlib.sha256(content).hexdigest() != plan['content_sha256']:
            raise DeployError('stale_plan')
        path = directory / Path(plan['target']).name
        stage = directory / Path(plan['staging_target']).name
        _target_absent(path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        try:
            fd = os.open(stage, flags, 0o600)
        except FileExistsError as exc:
            raise DeployError('staging_exists') from exc
        except OSError as exc:
            raise DeployError('write_failed') from exc
        file_identity = None
        try:
            st = os.fstat(fd)
            file_identity = (st.st_dev, st.st_ino)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise OSError('unsafe stage')
            remaining = memoryview(content)
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError('short write')
                remaining = remaining[written:]
            os.fsync(fd)
            os.close(fd)
            fd = None
        except OSError as exc:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if file_identity is None:
                raise DeployError('cleanup_unsafe') from exc
            _remove_stage(stage, file_identity)
            raise DeployError('write_failed') from exc
        # Сначала полная запись, fsync и повторная проверка байтов; ссылка не заменяет имя.
        if _stage_stat(stage, file_identity).st_nlink != 1:
            raise DeployError('cleanup_unsafe')
        try:
            valid = stage.read_bytes() == content
        except OSError as exc:
            _remove_stage(stage, file_identity)
            raise DeployError('write_failed') from exc
        if not valid:
            _remove_stage(stage, file_identity)
            raise DeployError('write_failed')
        try:
            os.link(stage, path)
        except FileExistsError as exc:
            _remove_stage(stage, file_identity)
            raise DeployError('target_exists') from exc
        except OSError as exc:
            _remove_stage(stage, file_identity)
            raise DeployError('publish_failed') from exc
        _remove_stage(stage, file_identity)
        try:
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != file_identity or st.st_nlink != 1:
                raise DeployError('created_unverified')
            if hashlib.sha256(path.read_bytes()).hexdigest() != plan['content_sha256']:
                raise DeployError('created_unverified')
        except OSError as exc:
            raise DeployError('created_unverified') from exc
        return {'outcome': 'created', 'target': plan['target'], 'content_sha256': plan['content_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--profile-root', required=True)
    args = parser.parse_args()
    session = KiloDeploymentSession(Layout(args.workspace, args.profile_root))
    while True:
        line = sys.stdin.buffer.readline(1_048_577)
        if not line:
            return 0
        if len(line) > 1_048_576:
            session.cancel()
            print(json.dumps({'outcome': 'error', 'code': 'input_too_large'}), flush=True)
            return 1
        try:
            obj = schema_v2.parse_json(line)
            if type(obj) is not dict:
                raise ValueError('request')
            if obj.get('type') == 'plan' and set(obj) == {'type','area','entry_id'}:
                result = session.plan(area=obj['area'], entry_id=obj['entry_id'])
            elif obj.get('type') == 'apply' and set(obj) == {'type','plan','confirmed_ticket'}:
                result = session.apply(obj['plan'], confirmed_ticket=obj['confirmed_ticket'])
            elif obj == {'type':'cancel'}:
                session.cancel(); result = {'outcome':'cancelled'}
            else:
                raise ValueError('request')
            print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        except StoreError as exc:
            print(json.dumps({'outcome':'error','diagnostic':exc.diagnostic()}, ensure_ascii=False), flush=True)
        except (DeployError, RenderError) as exc:
            print(json.dumps({'outcome':'error','code':getattr(exc, 'code', 'render_failed')}, ensure_ascii=False), flush=True)
        except (schema_v2.SchemaError, ValueError, TypeError, UnicodeError, RecursionError):
            session.cancel()
            print(json.dumps({'outcome':'error','code':'invalid_request'}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
