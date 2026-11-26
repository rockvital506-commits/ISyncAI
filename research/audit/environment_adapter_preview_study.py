#!/usr/bin/env python3
"""Непишущие предпросмотры Arena/Kilo/Copilot, не доставка и не средовые наблюдения."""
import hashlib

from kit import context_export, copilot_deploy, kilo_deploy
from kit.base import context_modes, registry_store
from kit.base.registry_policy import StoreError
from kit.render_rule import RenderError, render


class AdapterError(ValueError):pass


def _result(environment,content,*,target,inputs,scope,mode):
    return {'outcome':'preview_only','environment':environment,'content_utf8':content.decode('utf-8'),
            'content_sha256':hashlib.sha256(content).hexdigest(),'content_bytes':len(content),
            'target_hint':target,'inputs_sha256':dict(inputs),'scope':scope,'mode':mode,
            'created':'not_run','detected':'not_run','read':'not_run','applied':'not_run',
            'delivery':'not_performed','source_origin':'not_verified','authorization':'not_checked',
            'safety_completeness':'not_checked','context_budget':'not_measured'}


def arena(layout,*,mode,scope,choices):
    """Те же bytes, что подготовленный JSON-экспорт; передача в Arena не делается."""
    try:
        report=context_modes.prepare(layout,mode=mode,scope=scope,choices=choices)
        content=context_export._artifact(report)
        return _result('arena',content,target=None,inputs=report['inputs_sha256'],scope=scope,mode=mode)
    except StoreError as error:raise AdapterError('context_unavailable:'+error.code) from error
    except (ValueError,TypeError,RecursionError,UnicodeError) as error:raise AdapterError('context_invalid') from error


def instruction(layout,*,environment,area,entry_id):
    """Показывает глобальное правило; существующие записи/файлы среды не изменяются."""
    if environment not in ('kilo','copilot') or type(environment) is not str:
        raise AdapterError('environment_invalid')
    try:
        loaded=registry_store._load(layout)
        body=render(loaded.documents,area=area,entry_id=entry_id)
        if environment=='kilo':
            name=kilo_deploy.target_name(area,entry_id)
            content=body;target='.kilo/rules/'+name
        else:
            name=copilot_deploy._name(area,entry_id)
            content=copilot_deploy._PREFIX+body;target='.github/instructions/'+name
        return _result(environment,content,target=target,inputs=loaded.inputs_sha256,scope='.',mode=None)
    except StoreError as error:raise AdapterError('source_unavailable:'+error.code) from error
    except (RenderError,kilo_deploy.DeployError,ValueError,TypeError,RecursionError,UnicodeError) as error:
        raise AdapterError('rule_invalid') from error
