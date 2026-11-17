"""M2 build/verify/demo commands. Never calls a model or executes an agent."""

import argparse
import json
from pathlib import Path

from .contracts import ROOT
from .dataset_bundle import build_bundle, verify_bundle
from .intake import compile_session, confirm, new_session, reply
from .sales_cases import SPLITS


def demo_contract():
    fixture = json.loads((ROOT/'examples/sales-to-ppt/intake-conversation.json').read_text())
    session = new_session(fixture['messages'][0])
    session['session_id'] = 'sales-to-ppt-m2-demo'
    for message in fixture['messages'][1:]:
        session = reply(session,message)
    ready = compile_session(session)
    session = confirm(session,ready['review_sha256'],'synthetic-demo-reviewer')
    return compile_session(session)['contract']


def main(argv=None):
    parser = argparse.ArgumentParser(description='Lean-4-Agent-Eval M2：生成与独立核验销售到 PPT 评估集。')
    commands = parser.add_subparsers(dest='command',required=True)
    build = commands.add_parser('build',help='使用 M1 已确认合同和基准 CSV 构建数据集')
    build.add_argument('--contract',required=True)
    build.add_argument('--input',required=True)
    build.add_argument('--out',required=True)
    build.add_argument('--seed',type=int,default=42)
    build.add_argument('--split',action='append',choices=SPLITS)
    verify = commands.add_parser('verify',help='独立复算参考结果并执行评分器控制')
    verify.add_argument('--bundle',required=True)
    verify.add_argument('--contract',help='额外核对外部可信的已确认合同')
    demo = commands.add_parser('demo',help='合成 M1 确认 → M2 构建与核验，无真实 Agent')
    demo.add_argument('--out',default='.artifacts/m2-demo')
    demo.add_argument('--seed',type=int,default=42)
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify':
            contract = json.loads(Path(args.contract).read_text()) if args.contract else None
            report = verify_bundle(args.bundle,contract)
        elif args.command == 'demo':
            report = build_bundle(demo_contract(),(ROOT/'examples/sales-to-ppt/input/sales.csv').read_bytes(),args.out,args.seed)
        else:
            contract = json.loads(Path(args.contract).read_text())
            report = build_bundle(contract,Path(args.input).read_bytes(),args.out,args.seed,args.split or SPLITS)
        print(json.dumps({k:v for k,v in report.items() if k != 'controls'},ensure_ascii=False,indent=2))
        return 0
    except (ValueError,TypeError,KeyError,OSError) as exc:
        parser.exit(2, f'错误：{exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
