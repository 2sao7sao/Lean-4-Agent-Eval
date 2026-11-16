"""Local conversation and review commands. No provider credentials required."""

import argparse
import json
import os
from pathlib import Path
import tempfile

from .intake import compile_session, confirm, new_session, reply

ROOT = Path(__file__).resolve().parents[2]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.intake-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def review_markdown(result):
    if not result['contract']:
        return '# 需要澄清\n\n' + '\n'.join(f'- {q["prompt"]} {q["reason"]}' for q in result['questions']) + '\n'
    contract = result['contract']
    lines = ['# 评估合同审查', '', contract['goal'], '',
             f'状态：{result["state"]}；执行就绪：否；合同仍为 draft。', '',
             f'审查 SHA-256：`{result["review_sha256"]}`', '', '## 明确口径与来源', '',
             '| 字段 | 值 | 沟通来源 |', '|---|---|---|']
    labels = {'input_path':'输入文件','periods':'比较月份','data_model':'数据粒度','time_basis':'归月日期',
              'metric':'销售指标','status_policy':'纳入订单','currency_unit':'原始金额单位','refund_policy':'退款归属',
              'group_by':'拆分维度','analysis_scope':'分析范围','slide_count':'PPT 页数','language':'交付语言',
              'audience':'读者','external_policy':'外发权限'}
    values = {'order_snapshot':'订单快照 / 原订单月份','business_date':'订单业务日期','net_sales':'净销售额',
              'gross_sales':'毛销售额','paid_only':'仅已支付订单','contribution_only':'变化贡献；因果只作为待验证假设',
              'zh-CN':'中文','en':'英文','local_only':'仅本地交付，不外发','approval_required':'外发前需要作用域匹配的批准',
              'region':'地区','channel':'渠道','product':'产品'}
    for name, value in result['facts'].items():
        if name == 'periods':
            rendered = f'基期 {value["baseline"]}；对比期 {value["comparison"]}'
        elif name == 'currency_unit':
            units = {('CNY','minor'):'分',('CNY','major'):'人民币元',('USD','minor'):'美分',('USD','major'):'美元'}
            rendered = value['currency'] + ' / ' + units[(value['currency'], value['unit'])]
        elif name == 'data_model':
            rendered = '一行一订单的快照'
        elif name == 'refund_policy':
            rendered = '退款扣回原订单所属月份'
        elif isinstance(value, list):
            rendered = '、'.join(values.get(item, item) for item in value)
        else:
            rendered = values.get(str(value), str(value))
        rendered = rendered.replace('|', '\\|')
        turn = int(result['provenance'][name]['turn_id'][1:])
        lines.append(f'| {labels.get(name, name)} | {rendered} | 第 {turn} 轮 |')
    lines += ['', '## 编译器提议，确认时一并审查', '']
    lines += ['- ' + item for item in contract['assumptions']]
    lines += ['', '## 自动生成的验收标准', '', '| ID | 方法 | 条件 |', '|---|---|---|']
    methods = {'deterministic':'确定性检查','runtime_policy':'过程规则','human_review':'人工质量复核'}
    lines += [f'| {c["id"]} | {methods.get(c["method"], c["method"])} | {c["acceptance"].replace(chr(124), chr(92) + chr(124))} |' for c in contract['checks']]
    lines += ['', '## 后续执行条件', '', *['- ' + item for item in result['execution_blockers']], '',
              '此处确认需求口径与提议的验收标准，不批准业务执行或外发，也不证明检查器正确。', '']
    return '\n'.join(lines)


def export(session, directory):
    result = compile_session(session)
    if result['state'] == 'needs_clarification':
        raise ValueError('关键口径未补齐，不能导出完整合同。')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / 'session.json', session)
    write_json(directory / 'contract.json', result['contract'])
    write_json(directory / 'result.json', result)
    (directory / 'review.md').write_text(review_markdown(result), encoding='utf-8')
    return result


def summary(result):
    return {key:result[key] for key in ('state', 'session_id', 'questions', 'review_sha256', 'execution_ready')}


def run_demo(directory):
    fixture = json.loads((ROOT / 'examples/sales-to-ppt/intake-conversation.json').read_text())
    messages = fixture['messages']
    session = new_session(messages[0])
    session['session_id'] = 'sales-to-ppt-m1-demo'
    stages = [summary(compile_session(session))]
    for message in messages[1:]:
        session = reply(session, message)
        stages.append(summary(compile_session(session)))
    candidate = compile_session(session)
    if candidate['state'] != 'ready_for_review':
        raise ValueError('演示未能补齐关键口径。')
    session = confirm(session, candidate['review_sha256'], 'synthetic-demo-reviewer')
    result = export(session, directory)
    report = {'status':'PASS_FOR_M1_DEMO', 'scope':'Synthetic conversation replay and contract generation only.',
              'stages':[s['state'] for s in stages] + [result['state']],
              'user_turns':len(session['turns']), 'requirements':len(result['contract']['requirements']),
              'acceptance_checks':len(result['contract']['checks']), 'contract_status':result['contract']['status'],
              'execution_ready':False, 'agent_execution':'NOT_PERFORMED', 'output_directory':str(Path(directory)),
              'confirmation':'synthetic demo confirmation; not a real business approval'}
    write_json(Path(directory) / 'demo-report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Lean-4-Agent-Eval：销售分析到 PPT 的需求澄清与合同生成。')
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('intake', help='创建沟通记录并输出待澄清问题')
    start.add_argument('--request', required=True)
    start.add_argument('--session', default='.artifacts/intake/session.json')
    update = commands.add_parser('reply', help='补充或更正需求，已有确认会失效')
    update.add_argument('--session', required=True)
    update.add_argument('--message', required=True)
    update.add_argument('--field', help='仅针对一个问题 ID 回答，避免自由文本歧义')
    show = commands.add_parser('show', help='查看澄清问题或完整审查稿')
    show.add_argument('--session', required=True)
    accept = commands.add_parser('confirm', help='确认指定哈希的需求标准，不冻结执行')
    accept.add_argument('--session', required=True)
    accept.add_argument('--review-sha256', required=True)
    accept.add_argument('--by', required=True)
    output = commands.add_parser('export', help='导出合同 JSON、来源记录及 Markdown 审查稿')
    output.add_argument('--session', required=True)
    output.add_argument('--out', required=True)
    demo = commands.add_parser('demo', help='重放三条合成用户消息，无需模型 API')
    demo.add_argument('--out', default='.artifacts/m1-demo')
    chat = commands.add_parser('chat', help='交互式沟通，可逐轮补充多个字段')
    chat.add_argument('--request', required=True)
    chat.add_argument('--session', default='.artifacts/chat/session.json')
    chat.add_argument('--out', default='.artifacts/chat/export')
    chat.add_argument('--by', default='local-user')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            print(json.dumps(run_demo(args.out), ensure_ascii=False, indent=2))
            return 0
        path = Path(args.session)
        if args.command in ('intake', 'chat'):
            if path.exists():
                raise ValueError('会话文件已存在，请用 reply 继续或指定新的路径。')
            session = new_session(args.request)
        else:
            session = json.loads(path.read_text())
        if args.command == 'reply':
            session = reply(session, args.message, args.field)
        elif args.command == 'confirm':
            session = confirm(session, args.review_sha256, args.by)
        if args.command == 'chat':
            while True:
                result = compile_session(session)
                write_json(path, session)
                print(review_markdown(result))
                prompt = '补充口径（可一次回答多项；输入 退出 保存后结束）：'
                if result['state'] == 'ready_for_review':
                    prompt = '审查以上标准；输入 确认，或补充更正；输入 退出 保存：'
                try:
                    message = input(prompt).strip()
                except EOFError:
                    return 0
                if message in ('退出', 'exit', 'quit'):
                    return 0
                if message == '确认':
                    if result['state'] != 'ready_for_review':
                        print('关键口径未补齐，不能确认。')
                        continue
                    session = confirm(session, result['review_sha256'], args.by)
                    write_json(path, session)
                    print(json.dumps(summary(export(session, args.out)), ensure_ascii=False, indent=2))
                    return 0
                session = reply(session, message)
        result = compile_session(session)
        if args.command in ('intake', 'reply', 'confirm'):
            write_json(path, session)
        if args.command == 'show':
            print(review_markdown(result))
        elif args.command == 'export':
            print(json.dumps(summary(export(session, args.out)), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(summary(result), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'错误：{exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
