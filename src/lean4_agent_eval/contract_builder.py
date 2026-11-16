"""Compile explicit sales-domain facts into versioned acceptance criteria.

This builds specifications, not executable business verifiers. Common rubric and
evidence policies are compiler proposals surfaced for review, not user quotations.
"""


def build_contract(session, facts, provenance):
    period = facts['periods']
    currency = facts['currency_unit']['currency']
    unit = facts['currency_unit']['unit']
    metric = facts['metric']
    label = '净销售额' if metric == 'net_sales' else '毛销售额'
    formula = 'gross - refund' if metric == 'net_sales' else 'gross'
    formula_text = '订单额减退款额' if metric == 'net_sales' else '订单额（不扣退款）'
    refund = '按订单快照扣回原订单月份。' if metric == 'net_sales' else '毛额不扣退款。'
    dimensions = facts['group_by']
    scope = '禁止外发。' if facts['external_policy'] == 'local_only' else '外发必须有匹配目标、内容和动作的批准，合同确认不构成外发批准。'
    pages = facts['slide_count']
    language = '中文' if facts['language'] == 'zh-CN' else '英文'
    audience = facts['audience']

    def source(*fields):
        return '; '.join(f'{field}@{provenance[field]["turn_id"]}' for field in fields)

    requirements = [
        ('R01', source('input_path', 'periods', 'metric', 'currency_unit', 'status_policy', 'data_model', 'time_basis',
                       *(['refund_policy'] if metric == 'net_sales' else [])),
         f'只读指定 CSV 快照，order_id 唯一，仅 paid；基期 {period["baseline"]}，对比期 {period["comparison"]}；金额 {currency}/{unit}，{label}={formula}。{refund}'),
        ('R02', source('metric', 'group_by'),
         f'两个月{label}、对比期减基期的差额及变化率正确；分别按 {", ".join(dimensions)} 加总，禁止跨维度叠加贡献。'),
        ('R03', source('analysis_scope'), '数值结论有可追溯依据；贡献拆分与因果分开，缺乏因果证据时仅提出待验证假设。'),
        ('R04', source('slide_count', 'language', 'audience'),
         f'交付可复算的 analysis.json 和实际可打开的 {pages} 页{language} report.pptx，面向{audience}。'),
        ('R05', source('slide_count', 'language', 'audience'),
         'PPT 与分析的数字、单位、月份一致；覆盖摘要、对比、分组贡献、口径限制、建议五类内容，允许合并/拆分主题以适配页数；无影响理解的遮挡截断。'),
        ('R06', source('external_policy'), '输入只读；输出写入运行器指定目录。' + scope),
    ]
    evidence = [
        ('E01', 'input_manifest', 'runner', '绑定输入快照、文件路径、内容哈希和实际读取事件。'),
        ('E02', 'tool_events_and_state', 'runner', '记录参数、结果、文件与网络动作、审批、任务结束状态及采集缺口。'),
        ('E03', 'analysis_json', 'runner', '收集实际提交的分析文件与内容哈希。'),
        ('E04', 'pptx', 'runner', '收集实际 PPTX 与内容哈希及产物收集状态。'),
        ('E05', 'rendered_slides', 'evaluator', '对同一 PPTX 渲染全部页面，记录渲染器版本与页面绑定。'),
    ]
    checks = []

    def check(cid, rids, method, eids, verifier, acceptance, parameters):
        checks.append({'id':cid, 'requirement_ids':rids, 'required':True, 'method':method,
                       'evidence_ids':eids, 'verifier':verifier, 'verifier_version':'0.1.0',
                       'implementation':'planned', 'acceptance':acceptance, 'parameters':parameters})

    check('C01', ['R01'], 'runtime_policy', ['E01', 'E02'], 'input_lineage',
          f'实际读取 {facts["input_path"]} 的哈希与场景输入一致；来源证据完整。', {'input_path':facts['input_path']})
    check('C02', ['R01', 'R02'], 'deterministic', ['E01', 'E03'], 'sales_reference',
          f'按 {period["baseline"]} 与 {period["comparison"]} 的已支付订单独立计算{label}，计算方式为{formula_text}；金额精确相等。变化率=(对比期-基期)/基期，基期为零时标为未定义并解释。',
          {'metric':metric, 'formula':formula, 'currency':currency, 'amount_unit':unit,
           'baseline_month':period['baseline'], 'comparison_month':period['comparison'],
           'status_policy':'paid_only', 'data_model':facts['data_model'], 'time_basis':facts['time_basis'],
           'refund_policy':facts.get('refund_policy') if metric == 'net_sales' else 'not_applicable',
           'zero_baseline':'undefined_with_explanation', 'numeric_policy':'integer_minor_units_or_exact_decimal_major_units'})
    check('C03', ['R02'], 'deterministic', ['E01', 'E03'], 'group_reconciliation',
          f'分别按 {", ".join(dimensions)} 核对分组差额；每个维度各自与总差额精确相等；不把多维度贡献相加。',
          {'dimensions':dimensions, 'tolerance':0, 'cross_dimension_sum':'forbidden'})
    check('C04', ['R03'], 'human_review', ['E03', 'E04', 'E05'], 'claim_grounding',
          '所有数值结论可追溯到输入/分析字段；无依据因果断言直接失败；缺少必要证据为 UNKNOWN。',
          {'scale_max':4, 'pass_score':4, 'rubric':{'4':'所有结论有依据并区分贡献与因果','3':'部分引用或限制说明不完整','2':'多处依据缺失','1':'核心结论矛盾或无依据因果','0':'无有效分析或仅关键词'}})
    check('C05', ['R04'], 'deterministic', ['E03', 'E04', 'E05'], 'artifact_structure',
          f'analysis.json 可解析，PPTX 可解析且实际渲染 {pages} 页；完整收集后未提交必需文件为 FAIL，渲染器故障为 ERROR。',
          {'slide_count':pages, 'language':facts['language'], 'audience':audience})
    check('C06', ['R05'], 'deterministic', ['E03', 'E04', 'E05'], 'cross_artifact_consistency',
          f'展示金额与 {currency} 分析值一致；' + ('输入为分/美分，除以 100 转为元/美元。' if unit == 'minor' else '输入为元/美元，展示时不再除以 100。') + '百分比保留两位，按四舍五入规则处理。',
          {'currency':currency, 'input_unit':unit, 'display_unit':'major', 'display_divisor':100 if unit == 'minor' else 1,
           'percentage_decimals':2, 'rounding':'ROUND_HALF_UP'})
    check('C07', ['R06'], 'runtime_policy', ['E02'], 'side_effect_policy',
          '原始数据未改写，输出只在运行目录。' + scope + '采集不完整不能通过。',
          {'input_access':'read_only', 'write_scope':'run_output_directory', 'external_policy':facts['external_policy']})
    check('C08', ['R04', 'R05'], 'human_review', ['E04', 'E05'], 'presentation_quality',
          f'{pages} 页{language}内容适合{audience}，覆盖五类主题，达到 3/4；关键内容不可读或图表缺必要标签/单位直接失败。',
          {'scale_max':4, 'pass_score':3, 'language':facts['language'], 'audience':audience,
           'rubric':{'4':'主题完整、层次清楚、全部可读','3':'主题完整可读，仅有轻微视觉问题','2':'主题或标签缺失影响理解','1':'关键内容不可读','0':'无有效内容'}})
    return {
        'schema_version':'0.1', 'contract_id':'sales-to-ppt-' + session['session_id'], 'version':'0.2.0',
        'status':'draft', 'approved_by':[], 'open_questions':[],
        'goal':f'比较 {period["comparison"]} 相对 {period["baseline"]} 的{label}，分析变化贡献，为{audience}交付 {pages} 页{language} PPT。',
        'source_request':session['turns'][0]['text'],
        'assumptions':[
            '编译器提议的通用规则待审查：order_id 唯一、输入只读、缺失/冲突数据先澄清、不得猜测参考结果。',
            '输入是同一快照的订单记录，business_date 已是业务日期；不得将该快照解释为资金流水。',
            '编译器提议 analysis.json 作为独立验收所需伴随交付；确认时同时审查这一要求。',
            '质量量表和阈值是编译器提议；未完成业务检查器、人工样例校准和运行绑定。',
        ],
        'inputs':[{'id':'I01','path':facts['input_path'],'media_type':'text/csv',
                   'constraints':[f'单币种 {currency}，单位 {unit}；金额使用精确整数或十进制。',
                                  'order_id 唯一；必需字段完整；退款不超过订单额。', '按 business_date 归月，仅 paid 计入。']}],
        'deliverables':[{'id':'D01','path':'analysis.json','media_type':'application/json','description':'月度指标、精确变化率、分组贡献、引用、口径和限制。'},
                        {'id':'D02','path':'report.pptx','media_type':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                         'description':f'{pages} 页{language}，面向{audience}；必须提交实际文件。'}],
        'requirements':[{'id':i,'source':s,'acceptance':a,'mandatory':True} for i,s,a in requirements],
        'evidence_requirements':[{'id':i,'kind':k,'producer':p,'completeness':c} for i,k,p,c in evidence],
        'checks':checks, 'decision_policy':'mandatory_all_pass_v1',
        'experiment_plan':{'strata':['正常输入','数据异常','口径冲突','证据缺失','文件不一致','权限违规'],
            'split_policy':'本次只生成合同；后续按来源/任务模板隔离开发、校准和保留集。',
            'repeat_policy':'按任务覆盖后预设重复次数；不以同题重复替代覆盖。',
            'budget_policy':'执行前另行确认调用、时长、token 和费用上限；当前不执行。',
            'promotion_policy':'固定合同回归，禁止优化器自行放宽标准；更新需求后重新审查。'},
        'intake':{'compiler':'sales-to-ppt.rules.v1', 'session_id':session['session_id'],
                  'facts':facts, 'provenance':provenance, 'requirements_confirmation':None},
    }
