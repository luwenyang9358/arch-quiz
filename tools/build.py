#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把题库 JSON 注入模板，生成 app/index.html（单文件应用）。

优先使用 app/data/bank.json（由 tools/fetch_bank.py 生成），
不存在则退回 app/data/demo.json（仓库自带的 20 题演示数据）。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, 'app', 'src', 'index.tpl.html')
OUT = os.path.join(ROOT, 'app', 'index.html')
FULL = os.path.join(ROOT, 'app', 'data', 'bank.json')
DEMO = os.path.join(ROOT, 'app', 'data', 'demo.json')


def main():
    src = FULL if os.path.exists(FULL) else DEMO
    if not os.path.exists(src):
        sys.exit('找不到题库文件，请先运行 tools/fetch_bank.py')

    with open(src, encoding='utf-8') as f:
        data = json.load(f)
    bank = sorted(data.get('bank', []), key=lambda q: (q['year'], q['no']))
    sim = sorted(data.get('sim', []), key=lambda q: (q['year'], q['no']))
    cards = data.get('cards', [])

    with open(TPL, encoding='utf-8') as f:
        tpl = f.read()

    html = (tpl.replace('__BANK__', json.dumps(bank, ensure_ascii=False, separators=(',', ':')))
               .replace('__SIM__', json.dumps(sim, ensure_ascii=False, separators=(',', ':')))
               .replace('__CARDS__', json.dumps(cards, ensure_ascii=False, separators=(',', ':'))))

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    mode = '完整题库' if src == FULL else '演示数据'
    print(f"已生成 {OUT}（{len(html)/1024:.0f} KB）· {mode} · "
          f"真题 {len(bank)} / 模拟 {len(sim)} / 卡片 {len(cards)}")


if __name__ == '__main__':
    main()
