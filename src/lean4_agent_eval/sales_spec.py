"""M2 supports the confirmed M1 sales contract, not arbitrary unchecked rules."""

from datetime import date
from hashlib import sha256
import json
import re

from .contract_builder import build_contract
from .contracts import validate_contract

VERSION = 'sales-dataset.v1'
MAX_ROWS = 10000
MAX_AMOUNT_MINOR = 10**12
MAX_BYTES = 10 * 1024 * 1024


def digest(data):
    return sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def contract_digest(contract):
    return digest(json_bytes(contract))


def confirmed_spec(contract):
    errors = validate_contract(contract)
    if errors:
        raise ValueError('合同无效：' + '; '.join(errors))
    intake = contract.get('intake', {})
    if not intake.get('requirements_confirmation') or contract['open_questions']:
        raise ValueError('M2 要求 M1 已确认且没有未决问题的合同。')
    facts = intake['facts']
    try:
        if facts['metric'] not in ('net_sales', 'gross_sales'):
            raise ValueError('不支持的销售指标。')
        if facts['data_model'] != 'order_snapshot' or facts['time_basis'] != 'business_date' or facts['status_policy'] != 'paid_only':
            raise ValueError('M2 只支持订单快照、业务日期和 paid-only。')
        if facts['metric'] == 'net_sales' and facts['refund_policy'] != 'order_snapshot':
            raise ValueError('退款必须扣回原订单月份。')
        periods = facts['periods']
        for month in periods.values():
            if not re.fullmatch(r'20\d{2}-\d{2}', month):
                raise ValueError('月份必须为 YYYY-MM。')
            date.fromisoformat(month + '-01')
        if set(periods) != {'baseline', 'comparison'} or periods['baseline'] == periods['comparison']:
            raise ValueError('需要两个不同的明确月份。')
        units = facts['currency_unit']
        if units['currency'] not in ('CNY', 'USD') or units['unit'] not in ('minor', 'major'):
            raise ValueError('不支持的币种/金额单位。')
        dims = facts['group_by']
        if not dims or len(dims) != len(set(dims)) or not set(dims) <= {'region', 'channel', 'product'}:
            raise ValueError('不支持的分组维度。')
        if type(facts['slide_count']) is not int or not 3 <= facts['slide_count'] <= 20:
            raise ValueError('PPT 页数超出支持范围。')
        if facts['language'] not in ('zh-CN', 'en') or facts['analysis_scope'] != 'contribution_only':
            raise ValueError('不支持的语言或分析范围。')
        if facts['external_policy'] not in ('local_only', 'approval_required'):
            raise ValueError('不支持的外发规则。')
        # Do not silently ignore edits to confirmed acceptance rules.
        expected = build_contract({'session_id':intake['session_id'], 'turns':[{'text':contract['source_request']}]},
                                  facts, intake['provenance'])
        for key in ('requirements', 'checks', 'inputs', 'deliverables', 'assumptions', 'decision_policy'):
            if expected[key] != contract[key]:
                raise ValueError(f'确认合同的 {key} 已超出当前 M1 模板；需适配后才能生成。')
    except (KeyError, TypeError) as exc:
        raise ValueError('合同字段不完整或类型错误。') from exc
    return {'baseline':periods['baseline'], 'comparison':periods['comparison'],
            'metric':facts['metric'], 'currency':units['currency'], 'input_unit':units['unit'],
            'dimensions':list(dims), 'slide_count':facts['slide_count'], 'language':facts['language'],
            'audience':facts['audience'], 'external_policy':facts['external_policy']}


def columns(spec):
    amounts = ['gross_minor', 'refund_minor'] if spec['input_unit'] == 'minor' else ['gross_amount', 'refund_amount']
    return ['order_id', 'business_date', 'currency', 'payment_status', *amounts, *spec['dimensions']]
