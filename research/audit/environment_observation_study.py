#!/usr/bin/env python3
"""Форма наблюдений и арифметика бюджета, без доставки правил в среду."""

ENVIRONMENTS=('arena','kilo','copilot')
STATES=('created','detected','read','applied')


class ObservationError(ValueError):pass


def card(environment):
    if type(environment) is not str or environment not in ENVIRONMENTS:
        raise ObservationError('environment_invalid')
    return {'format':1,'environment':environment,'status':{name:'not_run' for name in STATES},
            'run_count':0,'model':None,'client_version':None,'mode':None,'settings':None,
            'material_sha256':None,'delivery_mechanism':None,'positive_control':None,
            'negative_control':None,'recorded_action':None,'interventions':None,
            'context_window_tokens':None,'injected_tokens':None,'token_measurement_source':None,
            'budget':'not_measured','independent_observer':'not_verified',
            'note':'template_only_no_evidence'}


def context_budget(*,window_tokens,injected_tokens,measurement_source):
    """Арифметика по сообщённым токенам; наличие/точность измерения не проверяются."""
    if (type(window_tokens) is not int or window_tokens<=0 or window_tokens>2**63-1 or
        type(injected_tokens) is not int or not 0<=injected_tokens<=window_tokens or
        type(measurement_source) is not str or not measurement_source.strip() or len(measurement_source)>1024):
        raise ObservationError('measurement_invalid')
    if injected_tokens*4<=window_tokens:result='at_or_below_25_percent'
    elif injected_tokens*10<=window_tokens*3:result='above_25_at_or_below_30_percent'
    else:result='above_30_percent'
    return {'outcome':'arithmetic_only','window_tokens':window_tokens,'injected_tokens':injected_tokens,
            'measurement_source':measurement_source,'budget_class':result,
            'target_25_percent_tokens_floor':window_tokens//4,
            'maximum_30_percent_tokens_floor':window_tokens*3//10,
            'measurement_accuracy':'not_verified','agent_detection':'not_verified',
            'agent_application':'not_verified','truncation':'not_checked'}
