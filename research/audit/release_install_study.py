#!/usr/bin/env python3
"""Синтетическая атомарная публикация снимка и нового workspace; не доверенная установка."""
import hashlib
import secrets
import threading

import release_archive_publish_study as publish
from kit import init_workspace as init
from kit.init_workspace import InitializationError


class InstallError(ValueError):
    pass


class _Combined(publish.PublishSession):
    def __init__(self, *args, profile_root, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile_root = profile_root

    def _capture(self):
        report, rows = super()._capture()
        source = dict(rows)
        try:
            l0 = source['kit/SYSTEM-L0.json']
            system_pin = hashlib.sha256(l0).hexdigest()
            workspace = init._files(l0, system_pin, self.profile_root)
        except (KeyError, InitializationError, ValueError, TypeError, RecursionError) as error:
            raise publish.PublishError('workspace_incompatible') from error
        # Поддеревья не перекрываются: snapshot_session требует отдельные корни.
        combined = [('snapshot/' + path, data) for path, data in rows]
        combined.extend(('workspace/' + path, data) for path, data in workspace.items())
        names = [name for name, _ in combined]
        if len(names) != len(set(names)) or any('/'.join(p.split('/')[:i]) in names
                for p in names for i in range(1, len(p.split('/')))):
            raise publish.PublishError('workspace_incompatible')
        report = dict(report, workspace_profile_root=self.profile_root,
                      workspace_system_sha256=system_pin, workspace_source='verified_archive_bytes',
                      workspace_semantics='not_checked')
        return report, tuple(sorted(combined))


class InstallSession:
    """Новый единый контейнер, один полный план и одно подтверждение; не recovery."""
    def __init__(self, destination, *, profile_root, archive_bytes, statement, signature, policy, verify_signature):
        self._inner = _Combined(destination, profile_root=profile_root, archive_bytes=archive_bytes,
                                statement=statement, signature=signature, policy=policy,
                                verify_signature=verify_signature)
        self._pending = None
        self._lock = threading.Lock()

    def cancel(self):
        if not self._lock.acquire(False): raise InstallError('session_busy')
        try:
            self._pending = None
            self._inner.cancel()
        finally: self._lock.release()

    def plan(self):
        if not self._lock.acquire(False): raise InstallError('session_busy')
        try:
            self._pending = None
            try: inner = self._inner.plan()
            except publish.PublishError as error: raise InstallError(str(error)) from error
            ticket = secrets.token_hex(32)
            shown = dict(inner); shown.pop('ticket')
            shown['effect'] = 'publish_new_snapshot_and_workspace'
            result = {'outcome':'planned', 'effect':'publish_new_snapshot_and_workspace',
                      'snapshot_root':inner['destination'] + '/snapshot',
                      'workspace_root':inner['destination'] + '/workspace',
                      'publication_plan':shown, 'ticket':ticket,
                      'authorization':'not_checked', 'trust_anchor':'assumed_not_verified',
                      'recovery':'not_performed', 'failure':'unknown_do_not_retry_or_delete'}
            self._pending = (init._canonical(result), inner, ticket)
            return result
        finally: self._lock.release()

    def apply(self, plan, *, confirmed_ticket):
        if not self._lock.acquire(False): raise InstallError('session_busy')
        try:
            if self._pending is None: raise InstallError('ticket_unknown')
            saved, inner, ticket = self._pending
            if (type(confirmed_ticket) is not str or len(confirmed_ticket) != 64 or
                    any(c not in '0123456789abcdef' for c in confirmed_ticket) or
                    not secrets.compare_digest(ticket, confirmed_ticket)):
                raise InstallError('confirmation_required')
            self._pending = None
            try:
                if type(plan) is not dict or init._canonical(plan) != saved:
                    self._inner.cancel(); raise InstallError('plan_mismatch')
            except (TypeError, ValueError, RecursionError) as error:
                self._inner.cancel()
                if isinstance(error, InstallError): raise
                raise InstallError('plan_mismatch') from error
            try: result = self._inner.apply(inner, confirmed_ticket=inner['ticket'])
            except publish.PublishError as error: raise InstallError(str(error)) from error
            return dict(result, outcome='study_container_published_unverified_origin',
                        snapshot_root=inner['destination'] + '/snapshot',
                        workspace_root=inner['destination'] + '/workspace',
                        recovery='not_performed')
        finally: self._lock.release()
