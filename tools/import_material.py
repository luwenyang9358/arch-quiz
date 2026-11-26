#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 tools/ocr_pdf.swift 产出的 OCR JSON 解析成 App 可用的题库 / 背诵卡。

用法：
  # 选择题（带答案与解析的讲义）
  python3 tools/import_material.py choice /tmp/ocr.json --out app/data/high.json --year 精选100

  # 背诵卡（案例 / 论文要点、论文范文）
  python3 tools/import_material.py cards /tmp/ocr.json --kind cf --label 案例提炼 --out app/data/cards_extra.json
  python3 tools/import_material.py cards /tmp/ocr.json --kind pf --label 论文提炼 --out app/data/cards_extra.json
  python3 tools/import_material.py cards /tmp/ocr.json --kind pf --label 论文范文 --mode essay --out app/data/cards_extra.json

设计约束：
  * 只处理文本层，不搬运原 PDF 的任何版式元素；
  * 页眉页脚、水印、机构标识一律按关键词过滤（见 BRAND），所以导入的内容里
    不会有第三方机构的标识或联系方式；
  * 原始 PDF 不入库，解析结果也建议只留在本地。
"""
import argparse
import json
import os
import re
import sys

# 导入第三方讲义时需要剔除的版式信息（机构名、水印、客服电话、页眉页脚）
BRAND = re.compile(r'希赛|xisaiwang|客服热线|内部资料|禁止传播|扫码|微信|加群|非学员|'
                   r'学员版本|在线职业教育|备考资料|客服|咨询|下载|公众号')

CHAP = re.compile(r'^([一二三四五六七八九十]+)、\s*(.+?)\s*[（(]\s*(\d+)\s*[)）]\s*$')
CHAP2 = re.compile(r'^(.{2,14}章节)\s*$')
QNUM = re.compile(r'^(\d{1,3})\s*[.、．]\s*(.+)$')
OPT = re.compile(r'^([A-H])\s*[.、．]\s*(.+)$')
ANS = re.compile(r'^答案\s*[:：]\s*([A-H]+)')
EXP = re.compile(r'^解析\s*[:：]\s*(.*)$')
ANS2 = re.compile(r'(?:正确答案|答案)\s*(?:是|为|选)?\s*[:：]?\s*([A-H](?:\s*[、,，]\s*[A-H])*)')


def lines_of(path):
    pages = json.load(open(path, encoding='utf-8'))
    out = []
    for p in pages:
        for l in p:
            t = (l.get('t') or '').strip()
            if not t or BRAND.search(t):
                continue
            y = l.get('y', 0.5)
            if y > 0.95 or y < 0.045:          # 页眉 / 页脚
                continue
            if re.fullmatch(r'\d+\s*/\s*\d+', t):
                continue
            out.append(t)
    return out


def join_cn(lines):
    """中文折行拼接：上一行没以标点结尾，就和下一行接起来"""
    s = ''
    for t in lines:
        if not s:
            s = t
            continue
        if re.search(r'[。！？；：:）)】”"]$', s) or re.match(r'^[（(]\d+[)）]|^\d+[)）]', t):
            s += '\n' + t
        else:
            s += t
    return s


# ---------------- 选择题 ----------------
def parse_choice(L, year):
    topic, expect, cur, blocks = '未分类', 1, None, []
    for t in L:
        m = CHAP.match(t)
        if m:
            topic = re.sub(r'\s+', '', m.group(2))
            if cur:
                blocks.append(cur)
                cur = None
            expect = 1                        # 讲义按章节重新编号
            continue
        m = QNUM.match(t)
        if m and int(m.group(1)) in (expect, expect + 1) and len(m.group(2)) > 1:
            if cur:
                blocks.append(cur)
            expect = int(m.group(1))
            cur = {'no': expect, 'topic': topic, 'lines': [m.group(2)]}
            expect += 1
            continue
        if cur is not None:
            cur['lines'].append(t)
    if cur:
        blocks.append(cur)

    qs = []
    for b in blocks:
        stem, groups, grp, ans, exp, mode = [], [], None, [], [], 'stem'
        for t in b['lines']:
            if mode == 'exp':
                exp.append(t)
                continue
            ma = ANS.match(t)
            if ma:
                ans = list(ma.group(1))
                mode = 'exp'
                continue
            me = EXP.match(t)
            if me:
                mode = 'exp'
                if me.group(1).strip():
                    exp.append(me.group(1).strip())
                continue
            mo = OPT.match(t)
            if mo and not ans:
                if grp is None or (grp['items'] and mo.group(1) <= grp['items'][-1]['k']):
                    grp = {'label': '', 'items': []}
                    groups.append(grp)
                grp['items'].append({'k': mo.group(1), 't': mo.group(2).strip()})
                mode = 'opt'
                continue
            if mode == 'stem':
                stem.append(t)
            elif mode == 'opt' and t and not t.startswith('答案'):
                grp['items'][-1]['t'] += t    # 选项折行

        stem_txt = ' '.join(stem).strip()
        exp_txt = re.sub(r'^解析\s*[:：]\s*', '', '\n'.join(exp).strip())
        if not ans:
            m = ANS2.search(exp_txt)
            if m:
                ans = re.findall(r'[A-H]', m.group(1))
        if not (groups and ans and stem_txt):
            continue
        if any(len(g['items']) < 2 for g in groups):
            continue
        q = {'stem': stem_txt, 'groups': groups, 'ans': ans, 'exp': exp_txt,
             'year': year, 'no': b['no'], 'topic': b['topic']}
        if len(ans) > 1 or len(groups) > 1:
            q['m'] = 1
        qs.append(q)
    return qs


# ---------------- 卡片 ----------------
ITEM = re.compile(r'^(\d{1,3})\s*[.、．]\s*(.+)$')
ESSAY_TITLE = re.compile(r'^论\s*[\u4e00-\u9fa5A-Za-z0-9（）()·\- ]{3,28}$')


def parse_items(L, kind, label):
    chap, items, cur = '', [], None
    for t in L:
        m = CHAP2.match(t)
        if m:
            if cur:
                items.append(cur)
                cur = None
            chap = m.group(1).replace('章节', '').strip()
            continue
        m = ITEM.match(t)
        if m and len(m.group(2)) > 3:
            if cur:
                items.append(cur)
            cur = {'title': m.group(2).rstrip('：:'), 'chapter': chap, 'lines': []}
            continue
        if cur is not None:
            cur['lines'].append(t)
    if cur:
        items.append(cur)

    out = []
    for i, it in enumerate(items, 1):
        body = join_cn(it['lines']).strip()
        if len(body) < 40:
            continue
        title = re.sub(r'[：:]\s*$', '', it['title'])
        out.append({'title': title, 'front': f'请说明：{title}', 'back': body, 'chapter': it['chapter'],
                    'k': kind, 'year': label, 'no': i, 'id': f'{kind}-{label}-{i}', 'src': label})
    return out


def parse_essay(L, kind, label):
    idx = [i for i, t in enumerate(L) if ESSAY_TITLE.match(t) and len(t) > 4]
    out = []
    for n, i in enumerate(idx, 1):
        end = idx[n] if n < len(idx) else len(L)
        chunk = L[i:end]
        cut = next((k for k, t in enumerate(chunk) if t.strip().startswith('范例')), len(chunk))
        head = [t for t in chunk[1:cut] if not re.match(r'^[”"“’’\'·\s]+$', t)]
        back = re.sub(r'^范例\s*', '', join_cn(chunk[cut:]).strip())
        if len(back) < 300:
            continue
        out.append({'title': chunk[0].strip(),
                    'front': (chunk[0].strip() + '\n\n' + join_cn(head).strip()).strip(),
                    'back': back, 'chapter': '', 'k': kind, 'year': label, 'no': n,
                    'id': f'{kind}-{label}-{n}', 'src': label})
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('choice', help='解析选择题')
    c.add_argument('ocr')
    c.add_argument('--out', default='app/data/high.json')
    c.add_argument('--year', default='精选100')

    k = sub.add_parser('cards', help='解析背诵卡')
    k.add_argument('ocr')
    k.add_argument('--out', default='app/data/cards_extra.json')
    k.add_argument('--kind', default='cf', choices=['case', 'paper', 'cf', 'pf'])
    k.add_argument('--label', default='提炼')
    k.add_argument('--mode', default='items', choices=['items', 'essay'])

    a = ap.parse_args()
    L = lines_of(a.ocr)

    if a.cmd == 'choice':
        data = parse_choice(L, a.year)
        print(f'解析 {len(data)} 题，多空题 {sum(1 for q in data if q.get("m"))} 道')
    else:
        data = parse_essay(L, a.kind, a.label) if a.mode == 'essay' \
            else parse_items(L, a.kind, a.label)
        print(f'解析 {len(data)} 张卡片')

    if not data:
        sys.exit('没有解析出内容，检查 OCR 质量或文档结构')

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    old = []
    if os.path.exists(a.out):
        old = json.load(open(a.out, encoding='utf-8'))

    def key(x):
        return x.get('id') or f"{x.get('year')}-{x.get('no')}"

    ids = {key(x) for x in old}
    merged = old + [x for x in data if key(x) not in ids]
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, separators=(',', ':'))
    print(f'写入 {a.out}（新增 {len(merged)-len(old)}，累计 {len(merged)}）')


if __name__ == '__main__':
    main()
