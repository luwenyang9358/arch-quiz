#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《综合知识》真题扫描件（OCR 结果）解析成题库 JSON。

前置：先用 tools/ocr_pdf.swift 把 PDF 转成 OCR JSON

    swiftc -O tools/ocr_pdf.swift -o /tmp/ocr_pdf
    /tmp/ocr_pdf "2009年下半年 综合知识.pdf"  /tmp/xa/ocr_2009_am.json
    /tmp/ocr_pdf "2009年下半年 答案详解.pdf" /tmp/xa/ocr_2009_ans.json

然后：

    python3 tools/parse_old_paper.py --ocr-dir /tmp/xa --out app/data/old.json

OCR JSON 结构：[[{t,x,y,w,h,c}, ...], ...]  按页分组的文本块，x/y 为归一化左上角坐标。

难点与对策
----------
1. 文本块顺序不可靠：同一视觉行内 y 有 ±0.01 抖动，选项还可能排成「2 行 2 列」。
   但同一视觉行内的文本块在 x 方向必然互不相交，而不同行的整行文本会在 x 上重叠。
   因此判定规则是「y 接近 且 x 区间不相交 ⇒ 同一行」，行内按 x 升序拼接即可还原。
2. 选项常被拆成多行（A、B 一行，C、D 一行），需按题号跨行累积，凑满 ABCD 才收题。
3. 原卷答案详解并不覆盖全部题目，缺答案的题直接丢弃（不猜）。
"""
import argparse
import glob
import json
import os
import re

# ---------------- 行还原 ----------------
def build_lines(page_items, y_tol=0.022, x_pad=0.006):
    lines = []
    for it in sorted(page_items, key=lambda z: (-z['y'], z['x'])):
        x0, x1 = it['x'], it['x'] + it['w']
        placed = False
        for ln in lines[-5:]:
            if abs(ln['y'] - it['y']) > y_tol:
                continue
            if all(x1 <= s[0] + x_pad or x0 >= s[0] + s[1] - x_pad for s in ln['segs']):
                ln['segs'].append((it['x'], it['w'], it['t']))
                placed = True
                break
        if not placed:
            lines.append({'y': it['y'], 'segs': [(it['x'], it['w'], it['t'])]})
    lines.sort(key=lambda l: -l['y'])
    return [(ln['y'], ''.join(s[2] for s in sorted(ln['segs']))) for ln in lines]


NOISE = [re.compile(p) for p in (
    r'软考达人', r'手机端题库', r'ruankaodaren', r'^你$', r'^\.?com$', r'ren\.com',
    r'第\s*\d+\s*页', r'共\s*\d+\s*页', r'^\s*20\d\d\s*年.*(上午|下午)', r'微信搜索',
    r'^\s*$', r'^[\s\d\.\-—_=·]+$', r'关注.*公众号', r'扫码', r'CTO说',
)]


def is_noise(t):
    return any(p.search(t) for p in NOISE)


# 选项标记：A. / B．/ C、，前面不能是字母数字（排除 R1（AC） 之类）
OPT = re.compile(r'(?<![A-Za-z0-9])(?:（(\d{1,2})）)?\s*([ABCD])\s*[\.．、]\s*')
ANS = re.compile(r'【?答案】?\s*([ABCD])')
BULLET = re.compile(r'^\s*[●•·]')


def stream_lines(path):
    pages = json.load(open(path, encoding='utf-8'))
    out = []
    for pi, pg in enumerate(pages):
        for y, t in build_lines(pg):
            if not is_noise(t):
                out.append((pi, y, t))
    return out


def looks_new_stem(line, last_no):
    """选项区中出现这种行，说明上一题结束、新题干开始"""
    if BULLET.match(line):
        return True
    m = re.search(r'[（(]\s*(\d{1,2})\s*[)）]', line)
    return bool(m and last_no and int(m.group(1)) == last_no + 1)


def parse_am(path):
    """解析题干 + 选项；返回 [{stem, groups:[(题号, {A..D})]}]"""
    blocks, stem_buf, groups, order = [], [], {}, []
    state, last_no = 'stem', 0

    def flush():
        nonlocal stem_buf, groups, order
        if groups:
            blocks.append({'stem': ''.join(stem_buf),
                           'groups': [(n, groups[n]) for n in order]})
        stem_buf, groups, order = [], {}, []

    for _, _, line in stream_lines(path):
        ms = list(OPT.finditer(line))
        if ms:
            for k, m in enumerate(ms):
                num, letter = m.group(1), m.group(2)
                end = ms[k + 1].start() if k + 1 < len(ms) else len(line)
                txt = line[m.end():end].strip()
                if letter == 'A':
                    no = int(num) if num is not None else last_no + 1
                    if no <= last_no and groups:      # 题号回卷 → 新块
                        flush()
                        stem_buf = []
                    groups.setdefault(no, {})
                    order.append(no)
                else:
                    no = order[-1] if order else (last_no or 1)
                    groups.setdefault(no, {})
                    if no not in order:
                        order.append(no)
                last_no = no
                if txt:
                    groups[no][letter] = groups[no].get(letter, '') + txt
            state = 'opt'
            continue
        if state == 'opt':
            if looks_new_stem(line, last_no):
                flush()
                stem_buf = [line]
                state = 'stem'
            elif order:
                no = order[-1]
                ks = [k for k in 'ABCD' if k in groups[no]]
                if ks:                              # 选项折行，续到最后一个选项
                    groups[no][ks[-1]] += line
        else:
            stem_buf.append(line)
    flush()
    return blocks


def parse_ans(path):
    """提取 {题号: 答案字母}"""
    res, last_no = {}, 0
    for _, _, line in stream_lines(path):
        for m in OPT.finditer(line):
            if m.group(2) == 'A':
                last_no = int(m.group(1)) if m.group(1) else last_no + 1
        a = ANS.search(line)
        if a and last_no and last_no not in res:
            res[last_no] = a.group(1)
    return res


def strip_ws(s):
    return re.sub(r'[\u200b\ufeff\s]', '', s)


def extract_exp(ans_path, stems):
    """用题干前缀定位每道题在答案卷中的起始行，从而界定上一条解析的结尾"""
    if not os.path.exists(ans_path):
        return {}
    CJK = re.compile(r'[^\u4e00-\u9fa5A-Za-z0-9]')
    key = lambda s: CJK.sub('', s)[:12]
    lines = [t for _, _, t in stream_lines(ans_path)]
    start_of = {}
    for i, ln in enumerate(lines):
        k = key(ln)
        if len(k) < 8:
            continue
        for no, st in stems.items():
            if no in start_of:
                continue
            ks = key(st)
            if len(ks) >= 8 and (k.startswith(ks) or ks.startswith(k)):
                start_of[no] = i
    starts = sorted(start_of.values())
    res, last_no = {}, 0
    for i, ln in enumerate(lines):
        for m in OPT.finditer(ln):
            if m.group(2) == 'A':
                last_no = int(m.group(1)) if m.group(1) else last_no + 1
        if '【解析】' in ln and last_no and last_no not in res:
            j = next((s for s in starts if s > i), min(len(lines), i + 40))
            body = ' '.join(lines[i:j])
            body = re.sub(r'^.*?【解析】', '', body, count=1)
            body = re.sub(r'手机端题库.*?com', '', body)
            body = re.sub(r'软考达人.*', '', body)
            body = re.sub(r'\s+', ' ', body).strip()
            if len(body) > 20:
                res[last_no] = body[:1200]
    return res


def fix_stem(stem, no):
    """把残留空号（（7）/ 7）/ _7））统一成（  ）；共享题干可能含相邻题号，取 ±5 窗口"""
    stem = stem.replace('●', '').replace('•', '')       # 题目项目符号
    stem = re.sub(r'^[·\-—\s]+', '', stem)

    def rep(m):
        return '（  ）' if abs(int(m.group(1)) - no) <= 5 else m.group(0)
    stem = re.sub(r'[（(_\-–—「]?\s*(\d{1,2})\s*[)）」]', rep, stem)
    return re.sub(r'（\s*）', '（  ）', stem).strip()


def bad_opt(t):
    return (not t) or len(t) > 120 or re.fullmatch(r'[\W_]+', t) is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ocr-dir', default='/tmp/xa', help='OCR JSON 所在目录')
    ap.add_argument('--out', default='app/data/old.json')
    ap.add_argument('--year-suffix', default='下半')
    args = ap.parse_args()

    out = []
    for f in sorted(glob.glob(os.path.join(args.ocr_dir, 'ocr_*_am.json'))):
        y = re.search(r'(\d{4})', os.path.basename(f)).group(1)
        blocks = parse_am(f)
        ansf = f.replace('_am', '_ans')
        ans = parse_ans(ansf) if os.path.exists(ansf) else {}
        year = y + args.year_suffix
        picked = []
        for b in blocks:
            stem = fix_stem(strip_ws(b['stem']), 0 if not b['groups'] else b['groups'][0][0])
            if len(stem) < 6:                          # 题干过短，多半是版面噪声
                continue
            for no, opts in b['groups']:
                if no not in ans or not all(k in opts for k in 'ABCD'):
                    continue
                if any(bad_opt(opts[k]) for k in 'ABCD'):
                    continue
                if len({opts[k] for k in 'ABCD'}) != 4:     # 选项重复，多半是 OCR 串行
                    continue
                picked.append({
                    'year': year, 'no': no,
                    'stem': fix_stem(strip_ws(b['stem']), no),
                    'groups': [{'label': '', 'items': [{'k': k, 't': opts[k]} for k in 'ABCD']}],
                    'ans': [ans[no]], 'exp': '',
                })
        # 只用校验通过的题干去定位解析区间，窗口更准
        exp = extract_exp(ansf, {q['no']: q['stem'] for q in picked})
        for q in picked:
            q['exp'] = exp.get(q['no'], '')
        out.extend(picked)
        print('%s 块 %d → 成题 %d（含解析 %d）'
              % (year, len(blocks), len(picked), sum(1 for q in picked if q['exp'])))

    out.sort(key=lambda q: (q['year'], q['no']))
    # 去重：同 year+no 只留一条；题干+选项相同的也去掉（OCR 跨页重复识别）
    seen, uniq = set(), []
    for q in out:
        k1 = (q['year'], q['no'])
        k2 = (q['stem'][:40], tuple(i['t'][:30] for i in q['groups'][0]['items']))
        if k1 in seen or k2 in seen:
            continue
        seen.update((k1, k2))
        uniq.append(q)
    out = uniq
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('共 %d 题，含解析 %d 题 → %s'
          % (len(out), sum(1 for q in out if q['exp']), args.out))


if __name__ == '__main__':
    main()
