"""Conservative, provider-free intake for monthly sales analysis to PPT.

Only explicit supported facts become slots. Missing, conflicting and unsupported
facts stay questions. This is a bounded rule parser, not general language understanding.
"""

import copy
import re
from uuid import uuid4

from .contract_builder import build_contract
from .contracts import review_hash, validate_contract

COMPILER = 'sales-to-ppt.rules.v1'
MISSING = object()
FIELDS = {
    'input_path': ('数据范围', '使用哪份 CSV？请给出文件路径，例如 input/sales.csv。'),
    'periods': ('数据范围', '请明确基期和对比期，例如：基期2026-09，对比期2026-10。相对日期不自动推断。'),
    'data_model': ('统计口径', '每行代表订单快照还是交易流水？本版支持一行一订单的订单快照。'),
    'time_basis': ('统计口径', '按哪个日期归月？本版支持订单业务日期 business_date；支付日期等口径需扩展。'),
    'metric': ('统计口径', '统计净销售额还是毛销售额？净额扣退款，毛额不扣退款。'),
    'status_policy': ('统计口径', '计入哪些订单状态？本版支持仅 paid / 已支付订单，其他口径需扩展。'),
    'currency_unit': ('统计口径', '原始金额的币种和单位是什么？例如：CNY 分、人民币元、USD cents。'),
    'refund_policy': ('统计口径', '退款如何归月？本版支持订单快照、退款扣回原订单月份；退款发生月流水口径需扩展。'),
    'group_by': ('分析与交付', '按哪些维度拆分贡献？可选地区 region、渠道 channel、产品 product，可多选。'),
    'analysis_scope': ('分析与交付', '仅做变化贡献分析并标注待验证假设，还是需要证实因果？本版支持变化贡献。'),
    'slide_count': ('分析与交付', 'PPT 需要几页？本版支持 3–20 页。'),
    'language': ('分析与交付', 'PPT 使用中文还是英文？'),
    'audience': ('分析与交付', 'PPT 面向谁？例如经营负责人、销售团队或客户。'),
    'external_policy': ('操作边界', '仅本地交付不外发，还是审批后外发？本版不支持免审批自动外发。'),
}


class Clarification(ValueError):
    pass


def _one(values, message):
    values = list(dict.fromkeys(values))
    if len(values) > 1:
        raise Clarification(message)
    return values[0] if values else MISSING


def _months(text):
    year = None
    months = []
    for match in re.finditer(r'(20\d{2})[-年/](\d{1,2})(?:月)?|(\d{1,2})月', text):
        if match[1]:
            year = match[1]
        if not year:
            continue
        month = int(match[2] or match[3])
        if not 1 <= month <= 12:
            raise Clarification('月份必须在 01–12 之间。')
        months.append(f'{year}-{month:02d}')
    if not months:
        return MISSING
    if len(months) != 2 or months[0] == months[1]:
        raise Clarification('请给出两个不同的绝对月份，并说明基期/对比期。')
    baseline = re.search(r'基期[：:\s]*(20\d{2})[-年/](\d{1,2})', text)
    comparison = re.search(r'对比期[：:\s]*(20\d{2})[-年/](\d{1,2})', text)
    if baseline and comparison:
        return {'baseline':f'{baseline[1]}-{int(baseline[2]):02d}',
                'comparison':f'{comparison[1]}-{int(comparison[2]):02d}'}
    if re.search(r'相对|相比|versus', text, re.I) and '基期' not in text:
        months.reverse()
    return {'baseline': months[0], 'comparison': months[1]}


def parse_field(field, text, explicit=False):
    lowered = text.lower()
    negative_forms = {
        'metric': r'(?:不要|不统计|不使用|不看)\s*(?:净销售额|毛销售额)',
        'status_policy': r'(?:不只|不仅|不限于|不限定).*?(?:paid|已支付)',
        'data_model': r'(?:不是|并非)\s*(?:订单快照|一行一订单)',
        'time_basis': r'不按\s*(?:订单业务日期|business_date)',
        'slide_count': r'(?:不要|不是|不用)\s*[\d一二三四五六七八九十两]+\s*页',
        'audience': r'不面向\s*(?:经营负责人|管理层|客户|销售团队)',
        'analysis_scope': r'(?:不做|不要)\s*(?:变化贡献|贡献分析)',
    }
    if field in negative_forms and re.search(negative_forms[field], lowered):
        raise Clarification('该字段包含否定，请直接给出最终采用的值。')
    if field == 'input_path':
        quoted = re.findall(r'["`“]([^"`”]+\.csv)["`”]', text, re.I)
        values = quoted or re.findall(r'(?<![a-zA-Z0-9_./-])([a-zA-Z0-9_./-]+\.csv)\b', text, re.I)
        if explicit and text.strip().lower().endswith('.csv'):
            values = [text.strip()]
        return _one(values, '本版每个任务使用一份订单快照 CSV，请明确输入文件。')
    if field == 'periods':
        # Restrict parsing to clauses containing a year; don't read page counts as months.
        without_paths = re.sub(r'[^\s，,；;。\n]+\.csv', '', text)
        if re.search(r'20\d{2}[-年/]\d{1,2}[-月/]\d{1,2}|\d{1,2}日', without_paths):
            raise Clarification('按日区间尚未支持，请明确两个完整月份或扩展日期规则。')
        clauses = re.split(r'[；;。\n]', without_paths)
        dated = [c for c in clauses if re.search(r'20\d{2}[-年/]', c)]
        if any(re.search(r'或|还是', clause) for clause in dated):
            raise Clarification('月份存在备选，请明确基期和对比期。')
        return _months('；'.join(dated)) if dated else MISSING
    if field == 'data_model':
        if re.search(r'交易流水|逐笔流水|transaction ledger', lowered):
            raise Clarification('交易流水尚未支持，不能按一行一订单解释。')
        if re.search(r'订单快照|一行一订单|order_snapshot', lowered):
            return 'order_snapshot'
    if field == 'time_basis':
        if re.search(r'按支付日期|按付款日期|支付日期归月|paid_at', lowered):
            raise Clarification('按支付日期归月需要新的映射规则，目前支持订单业务日期。')
        if re.search(r'订单业务日期|business_date|业务日期归月', lowered):
            return 'business_date'
    if field == 'metric':
        if re.search(r'净销售额[^；;。]*(?:不扣|不减)|毛销售额[^；;。]*(?:需要|必须|要)(?:扣|减)', text):
            raise Clarification('指标名称与退款处理矛盾：净额扣退款，毛额不扣退款，请明确最终定义。')
        values = []
        if re.search(r'净销售额|net_sales|net sales', lowered):
            values.append('net_sales')
        if re.search(r'毛销售额|销售毛额|gross_sales|gross sales', lowered):
            values.append('gross_sales')
        return _one(values, '同时出现净销售额和毛销售额，请指定本次主要验收指标。')
    if field == 'status_policy':
        if re.search(r'所有订单|全部订单|包括未支付|all orders', lowered):
            raise Clarification('全部状态加总超出当前 paid-only 口径；请澄清或扩展领域规则。')
        if re.search(r'(?:仅|只有|只)(?:统计|计算|计入|纳入)?\s*(?:paid|已支付|已付款)|paid_only', lowered):
            return 'paid_only'
        if explicit and lowered.strip() in ('paid', '已支付', '已付款'):
            return 'paid_only'
    if field == 'currency_unit':
        clauses = re.split(r'[；;。\n]', text)
        scoped = [c for c in clauses if re.search(r'原始金额|输入金额|金额单位|数据金额', c)]
        selected = '；'.join(scoped) if scoped else text
        if re.search(r'分.*(?:或|还是).*元|元.*(?:或|还是).*分', selected):
            raise Clarification('单位存在备选，请明确使用元还是分。')
        currencies = []
        for currency, pattern in [('CNY', r'cny|rmb|人民币'), ('USD', r'usd|美元')]:
            if re.search(pattern, selected, re.I):
                currencies.append(currency)
        currency = _one(currencies, '多币种数据需要明确换算规则，当前只支持单币种。')
        if currency is MISSING:
            return MISSING
        tokens = re.findall(r'(?:cny|usd|rmb|人民币|美元|金额单位|单位)\s*(?:为|是|：|:)?\s*(分|元|cents?|dollars?|minor|major)', selected, re.I)
        units = ['minor' if token.lower() in ('分', 'cent', 'cents', 'minor') else 'major' for token in tokens]
        unit = _one(units, '同时出现元和分，请明确原始输入金额的单位。')
        return {'currency': currency, 'unit': unit} if unit is not MISSING else MISSING
    if field == 'refund_policy':
        if re.search(r'退款发生月|退款流水|按退款日期|transaction_period', lowered):
            raise Clarification('退款发生月流水口径尚未支持，不能替换成订单快照。')
        if re.search(r'原订单月|原订单所属月|原订单月份|refund_to_order_month', lowered):
            return 'order_snapshot'
    if field == 'group_by':
        if re.search(r'不按|不要按|而不是', text) and re.search(r'地区|区域|渠道|产品|region|channel|product', lowered):
            raise Clarification('维度包含否定或替代关系，请仅列出最终需要的维度。')
        found = [key for key, pattern in [('region', r'地区|区域|region'), ('channel', r'渠道|channel'), ('product', r'产品|product')]
                 if re.search(pattern, lowered)]
        return found or MISSING
    if field == 'analysis_scope':
        if re.search(r'证明因果|证实因果|确定原因|因果验证|causal proof', lowered):
            raise Clarification('仅销售快照无法证实因果；需要额外证据和新的检查器。可明确选择变化贡献分析。')
        if re.search(r'变化贡献|贡献分析|贡献拆分|contribution', lowered):
            return 'contribution_only'
    if field == 'slide_count':
        counts = re.findall(r'(\d+)\s*(?:页|slides?)', lowered)
        if explicit and text.strip().isdigit():
            counts.append(text.strip())
        chinese = {'一':1, '二':2, '两':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9}
        for token in re.findall(r'([一二三四五六七八九十两]+)页', text):
            if token in chinese:
                counts.append(str(chinese[token]))
            elif token.count('十') == 1:
                tens, ones = token.split('十')
                if tens not in ('', *chinese) or ones not in ('', *chinese):
                    raise Clarification('请使用明确的阿拉伯数字页数。')
                counts.append(str((chinese[tens] if tens else 1) * 10 + (chinese[ones] if ones else 0)))
            else:
                raise Clarification('请使用明确的阿拉伯数字页数。')
        value = _one([int(n) for n in counts], 'PPT 页数冲突，请指定一个页数。')
        if value is not MISSING and not 3 <= value <= 20:
            raise Clarification('本版支持 3–20 页；其他篇幅需明确新的交付模板。')
        return value
    if field == 'language':
        values = []
        if re.search(r'中文|chinese', lowered):
            values.append('zh-CN')
        if re.search(r'英文|english', lowered):
            values.append('en')
        return _one(values, '双语交付尚未支持，请指定一个语言或扩展模板。')
    if field == 'audience':
        match = re.search(r'(?:面向|受众[为是：:]?|给|供)\s*(经营负责人|管理层|业务负责人|销售团队|业务团队|客户|老板|投资人)', text)
        if match:
            return match[1]
        if explicit and 1 <= len(text.strip()) <= 80:
            return text.strip()
    if field == 'external_policy':
        if re.search(r'无需审批.*(?:外发|发送)|自动(?:外发|发送)|直接(?:外发|发送)', text):
            raise Clarification('免审批外发不受支持；请明确仅本地交付或审批后外发。')
        values = []
        if re.search(r'不外发|不要外发|禁止外发|仅本地交付|local_only', lowered):
            values.append('local_only')
        if re.search(r'审批后外发|批准后外发|需要审批|经批准.*外发|approval_required', lowered):
            values.append('approval_required')
        return _one(values, '外发规则冲突，请明确禁止外发还是审批后外发。')
    return MISSING


def new_session(request):
    if not isinstance(request, str) or not request.strip():
        raise ValueError('需求不能为空。')
    return {'schema_version':'intake.v1', 'session_id':str(uuid4()),
            'turns':[{'id':'T001','text':request.strip(),'field':None}], 'confirmation':None}


def reply(session, text, field=None):
    if field is not None and field not in FIELDS:
        raise ValueError(f'未知澄清字段：{field}')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('补充内容不能为空。')
    result = copy.deepcopy(session)
    result['turns'].append({'id':f'T{len(result["turns"]) + 1:03d}', 'text':text.strip(), 'field':field})
    result['confirmation'] = None
    return result


def _facts(session):
    if session.get('schema_version') != 'intake.v1' or not session.get('session_id') or not session.get('turns'):
        raise ValueError('无效的沟通记录。')
    facts, provenance, problems = {}, {}, {}
    for index, turn in enumerate(session['turns'], 1):
        if turn.get('id') != f'T{index:03d}' or not isinstance(turn.get('text'), str) or not turn['text'].strip():
            raise ValueError('沟通轮次必须连续且文本非空。')
        field = turn.get('field')
        if field is not None and field not in FIELDS:
            raise ValueError('沟通记录包含未知字段。')
        text = turn['text']
        if text == '撤回上一条未识别补充':
            problems.pop('unhandled', None)
            continue
        scoped_text = re.sub(r'(?:不需要|无需|不要|不做|不)(?:做)?(?:预测|forecast|因果验证)', '', text, flags=re.I)
        unsupported = re.search(r'预测|forecast|季度|同比|利润|毛利|数据库|多币种', scoped_text, re.I)
        if unsupported:
            problems['unhandled'] = f'“{unsupported[0]}”超出当前月度销售快照到 PPT 模板，不能静默忽略。需要扩展模板，或明确撤回这项补充。'
        hits = 0
        for name in ([field] if field else FIELDS):
            try:
                value = parse_field(name, text, explicit=field is not None)
            except Clarification as exc:
                problems[name] = str(exc)
                hits += 1
                continue
            if value is MISSING:
                continue
            hits += 1
            if re.search(r'不确定|也许|可能|大概|是不是|是否', text):
                problems[name] = '表述带有不确定性，请确认后再给出该字段。'
                continue
            if name in facts and facts[name] != value and not re.search(r'更正|改为|改成|correction', text, re.I):
                problems[name] = f'前后口径冲突：已有 {facts[name]}，新内容为 {value}。请用“更正：…”指定最终值。'
                continue
            facts[name] = value
            provenance[name] = {'turn_id':turn['id'], 'excerpt':text}
            problems.pop(name, None)
        if field and not hits:
            problems[field] = '无法识别这个回答；请使用问题中列出的表述。'
        elif not hits and index > 1:
            problems['unhandled'] = '未识别这条补充，不能自动纳入合同。请按字段澄清，或明确输入“撤回上一条未识别补充”。'
    return facts, provenance, problems


def compile_session(session):
    facts, provenance, problems = _facts(session)
    required = [f for f in FIELDS if f != 'refund_policy' or facts.get('metric') != 'gross_sales']
    questions = []
    for field in required:
        if field not in facts or field in problems:
            group, prompt = FIELDS[field]
            questions.append({'id':field,'group':group,'prompt':prompt,'reason':problems.get(field, '尚未明确。')})
    if 'unhandled' in problems:
        questions.append({'id':'unhandled','group':'补充需求','prompt':problems['unhandled'],'reason':'未支持的自由文本。'})
    result = {'compiler':COMPILER, 'session_id':session['session_id'], 'facts':facts,
              'provenance':provenance, 'questions':questions, 'contract':None,
              'review_sha256':None, 'state':'needs_clarification', 'execution_ready':False}
    if questions:
        return result
    contract = build_contract(session, facts, provenance)
    errors = validate_contract(contract)
    if errors:
        raise ValueError('生成合同未通过校验：' + '; '.join(errors))
    digest = review_hash(contract)
    confirmation = session.get('confirmation')
    if confirmation and confirmation.get('review_sha256') != digest:
        raise ValueError('确认记录与当前合同不匹配，请重新审查。')
    if confirmation:
        contract['intake']['requirements_confirmation'] = confirmation
        errors = validate_contract(contract)
        if errors:
            raise ValueError('确认记录无效：' + '; '.join(errors))
    result.update(contract=contract, review_sha256=digest,
                  state='requirements_confirmed' if confirmation else 'ready_for_review',
                  execution_blockers=['必检业务验收器仍待实现与校准。', '尚未建立真实 Agent 与证据采集适配器。'])
    return result


def confirm(session, review_sha256, confirmed_by):
    result = compile_session(session)
    if result['state'] != 'ready_for_review' or review_sha256 != result['review_sha256']:
        raise ValueError('只能确认当前已补齐口径的合同，且审查哈希必须匹配。')
    if not confirmed_by.strip():
        raise ValueError('确认人不能为空。')
    updated = copy.deepcopy(session)
    updated['confirmation'] = {'review_sha256':review_sha256,'confirmed_by':confirmed_by.strip()}
    return updated


class SalesSpecCompiler:
    """SpecCompiler implementation returning a clarification/review envelope."""

    def compile(self, request, answers):
        session = new_session(request)
        for field, answer in answers.items():
            session = reply(session, answer, field=field)
        return compile_session(session)
