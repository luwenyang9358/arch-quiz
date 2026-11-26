#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把题库 JSON 注入模板，生成 app/index.html（单文件应用）。

数据来源（按优先级）：
  app/data/bank.json   由 tools/fetch_bank.py 生成（真题 / 模拟 / 卡片）
  app/data/demo.json   仓库自带的演示数据
另外可选（不存在就跳过）：
  app/data/high.json        额外的高频题（如 tools/import_material.py 产出）
  app/data/cards_extra.json 额外的背诵卡
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, 'app', 'src', 'index.tpl.html')
OUT = os.path.join(ROOT, 'app', 'index.html')
DATA = os.path.join(ROOT, 'app', 'data')
FULL = os.path.join(DATA, 'bank.json')
DEMO = os.path.join(DATA, 'demo.json')
HIGH = os.path.join(DATA, 'high.json')
EXTRA = os.path.join(DATA, 'cards_extra.json')


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main():
    src = FULL if os.path.exists(FULL) else DEMO
    if not os.path.exists(src):
        sys.exit('找不到题库文件，请先运行 tools/fetch_bank.py')

    data = load(src) or {}
    bank = sorted(data.get('bank', []), key=lambda q: (q['year'], q['no']))
    sim = sorted(data.get('sim', []), key=lambda q: (q['year'], q['no']))
    cards = list(data.get('cards', []))

    high = sorted(load(HIGH) or [], key=lambda q: (q.get('topic', ''), q['no']))
    extra = load(EXTRA) or []
    if extra:
        seen = {c['id'] for c in cards}
        cards += [c for c in extra if c['id'] not in seen]

    with open(TPL, encoding='utf-8') as f:
        tpl = f.read()

    def js(v):
        return json.dumps(v, ensure_ascii=False, separators=(',', ':'))

    html = (tpl.replace('__BANK__', js(bank))
               .replace('__SIM__', js(sim))
               .replace('__HIGH__', js(high))
               .replace('__CARDS__', js(cards)))

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    mode = '完整题库' if src == FULL else '演示数据'
    print(f"已生成 {OUT}（{len(html)/1024:.0f} KB）· {mode} · "
          f"真题 {len(bank)} / 模拟 {len(sim)} / 高频 {len(high)} / 卡片 {len(cards)}")


if __name__ == '__main__':
    main()
