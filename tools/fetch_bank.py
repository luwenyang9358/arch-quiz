#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从公开的社区题库仓库抓取「系统架构设计师」资料，解析为 App 需要的 bank.json。

数据来源（均为公开仓库，非官方发布）：
  https://github.com/wujiaming88/awesome-ruankao
    - 真题/系统架构设计师/{年份}/综合知识.md          → 单选真题
    - 模拟题/系统架构设计师/2026年5月/模拟卷N/综合知识_{题目,答案}.md → 模拟题
    - 真题/系统架构设计师/{年份}/案例分析.md          → 背诵卡（案例）
    - 真题/系统架构设计师/{年份}/论文.md              → 背诵卡（论文）

用法：
    python3 tools/fetch_bank.py            # 输出 app/data/bank.json
    python3 tools/fetch_bank.py --demo 20  # 只取 20 题做演示数据

说明：题目版权归原命题机构，本脚本仅做个人备考用的格式转换，请勿二次分发题库内容。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

RAW = "https://raw.githubusercontent.com/wujiaming88/awesome-ruankao/main/"
TIMEOUT = 60
RETRY = 3

YEARS = ["2020年下半年", "2021年下半年", "2022年下半年", "2023年下半年",
         "2024年上半年", "2024年下半年", "2025年上半年", "2025年下半年", "2026年上半年"]
SIMS = [f"模拟卷{i}" for i in range(1, 8)]

OPT = re.compile(r'^\s*(?:[-*+]\s*)?([A-H])\s*[.、．:：]\s*(.*)$')
HEAD = re.compile(r'^(?:#{2,4}\s*)?第\s*(\d+)\s*题')


def fetch(rel_path, retry=RETRY):
    url = RAW + urllib.parse.quote(rel_path)
    for i in range(retry):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
                return r.read().decode('utf-8', 'ignore').replace('\u0000', '')
        except Exception as e:
            if i == retry - 1:
                print(f"  ! 下载失败 {rel_path}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 * (i + 1))


def blocks(text):
    """按「第N题」切块，返回 {题号: 块文本}"""
    out = {}
    for part in re.split(r'\n(?=#{2,4}\s*第\s*\d+\s*题)', text)[1:]:
        m = HEAD.match(part.split('\n')[0].strip())
        if m:
            out[int(m.group(1))] = part
    return out


def parse_choice(part):
    """解析一道单选题：题干、选项组、答案、解析、考点"""
    flat_lines = part.split('\n')[1:]
    stem, groups, ans, exp, sub = [], [], [], [], ''
    grp = None
    for raw in flat_lines:
        s = raw.strip()
        if not s or re.match(r'^-{3,}$', s):
            continue
        f = s.replace('**', '').strip()
        mh = re.match(r'^选项\s*(（[^）]*）)?\s*[:：]?\s*$', f)
        if mh and not ans:
            grp = {'label': (mh.group(1) or '').strip('（）'), 'items': []}
            groups.append(grp)
            continue
        mo = OPT.match(s)
        if mo and not ans:
            if grp is None:
                grp = {'label': '', 'items': []}
                groups.append(grp)
            grp['items'].append({'k': mo.group(1), 't': mo.group(2).strip()})
            continue
        ma = re.match(r'^(?:验证)?(?:答案|参考答案|正确答案)\s*[:：]\s*(.+)$', f)
        if ma:
            ans = re.findall(r'[A-H]', ma.group(1))
            continue
        me = re.match(r'^(解析|验证依据|答案解析)\s*[:：]?\s*(.*)$', f)
        if me:
            if me.group(2).strip():
                exp.append(me.group(2).strip())
            continue
        mt = re.match(r'^考点\s*[:：]\s*(.+)$', f)
        if mt:
            sub = mt.group(1).strip()
            continue
        if ans:
            exp.append(re.sub(r'^\s*[-*+]\s+', '· ', s))
        else:
            stem.append(s)

    stem_txt = ' '.join(stem)
    stem_txt = re.sub(r'^\*\*(题目|题干|问题)\*\*\s*[:：]\s*', '', stem_txt).strip()
    valid = groups and ans and all(len(g['items']) >= 2 for g in groups) and stem_txt
    if not valid:
        return None
    q = {'stem': stem_txt, 'groups': groups, 'ans': ans, 'exp': '\n'.join(exp).strip()}
    if len(ans) > 1 or len(groups) > 1:
        q['m'] = 1          # 多空题：选项与答案不是一一对应，需人工判定
    if sub:
        q['sub'] = sub
    return q


# ---------- 考点归一化（模拟题按章节标题归类） ----------
def norm_topic(t):
    rules = [('计算机', '计算机基础'), ('软件工程', '软件工程'), ('架构', '软件架构'),
             ('安全', '信息安全'), ('数据库', '数据库'), ('新技术', '新技术'), ('AI', '新技术'),
             ('英语', '英语'), ('可靠性', '系统可靠性'), ('性能', '系统可靠性'),
             ('知识产权', '知识产权与法律'), ('法律', '知识产权与法律')]
    for k, v in rules:
        if k in t:
            return v
    return '未分类'


def sim_topics(text):
    """从章节标题（## 一、计算机基础（第1-10题））推每题的考点"""
    sec, mp = '未分类', {}
    for line in text.split('\n'):
        m = re.match(r'^##\s*(?:[一二三四五六七八九十]+[、.．]\s*)?(.+?)(（第.+?题）)?\s*$', line)
        if m and not line.startswith('###'):
            sec = norm_topic(m.group(1))
        h = HEAD.match(line)
        if h:
            mp[int(h.group(1))] = sec
    return mp


def load_real_choice():
    out = []
    for y in YEARS:
        txt = fetch(f"真题/系统架构设计师/{y}/综合知识.md")
        if not txt:
            continue
        year = y.replace('年', '').replace('半年', '')
        n = 0
        for no, part in sorted(blocks(txt).items()):
            q = parse_choice(part)
            if q:
                out.append(dict(q, year=year, no=no))
                n += 1
        print(f"  真题 {year}: {n} 题")
    return out


def load_sim():
    out = []
    for s in SIMS:
        tag = s.replace('模拟卷', '模拟')
        qt = fetch(f"模拟题/系统架构设计师/2026年5月/{s}/综合知识_题目.md")
        at = fetch(f"模拟题/系统架构设计师/2026年5月/{s}/综合知识_答案.md")
        if not qt or not at:
            continue
        topics = sim_topics(qt)
        ab = blocks(at)
        n = 0
        for no, part in sorted(blocks(qt).items()):
            q = parse_choice(part)
            if not q:
                continue
            a = ab.get(no, '')
            ma = re.search(r'\*\*答案\*\*\s*[:：]\s*(.+)', a)
            me = re.search(r'\*\*解析\*\*\s*[:：]\s*(.+)', a)
            ms = re.search(r'\*\*考点\*\*\s*[:：]\s*(.+)', a)
            if ma:
                q['ans'] = re.findall(r'[A-H]', ma.group(1))
            if me:
                q['exp'] = me.group(1).strip()
            if ms:
                q['sub'] = ms.group(1).strip()
            q['topic'] = topics.get(no, '未分类')
            q['year'], q['no'], q['sim'] = tag, no, 1
            out.append(q)
            n += 1
        print(f"  模拟 {tag}: {n} 题")
    return out


# ---------- 背诵卡 ----------
ANS_MARKS = ["【参考答案】", "【答案】", "**参考答案", "**答案", "参考答案：", "答案：",
             "【答题要点】", "【题型分析】"]
PAPER_MARKS = ["### 写作要点", "### 写作思路", "**写作要点", "**解析", "### 范文"]


def clean(t):
    t = re.sub(r'\*{2,}', '', t)
    t = re.sub(r'(?m)^#{1,6}[ \t]*$\n?', '', t)     # 源文档里残留的空标题行（单独的 ###）
    t = re.sub(r'[ \t]+\n', '\n', t)
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def split_cards(text, pattern, marks):
    ms = list(re.finditer(pattern, text, re.M))
    out = []
    for i, m in enumerate(ms):
        title = re.sub(r'^#+\s*', '', m.group(0)).strip()
        body = text[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        cut = len(body)
        for mk in marks:
            j = body.find(mk)
            if j != -1:
                cut = min(cut, j)
        out.append({'title': title, 'front': clean(body[:cut]), 'back': clean(body[cut:])})
    return out


def load_cards():
    cards = []
    cp = r'^#{1,4}\s*(?:[\d.]+\s*)?试题\s*[一二三四五1-5][^\n]*$'
    pp = r'^#{1,3}\s*(?:[\d.]+\s*)?试题\s*[一二三四五1-5][^\n]*$'
    for y in YEARS:
        year = y.replace('年', '').replace('半年', '')
        t = fetch(f"真题/系统架构设计师/{y}/案例分析.md")
        if t:
            for n, c in enumerate(split_cards(t, cp, ANS_MARKS), 1):
                cards.append(dict(c, id=f'c-{year}-{n}', k='case', year=year, no=n))
        t = fetch(f"真题/系统架构设计师/{y}/论文.md")
        if t:
            for n, c in enumerate(split_cards(t, pp, PAPER_MARKS), 1):
                cards.append(dict(c, id=f'p-{year}-{n}', k='paper', year=year, no=n))
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--demo', type=int, default=0, help='只保留 N 道题作为演示数据')
    ap.add_argument('-o', '--out', default=None)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = args.out or os.path.join(root, 'app', 'data', 'bank.json')

    print('抓取真题…')
    bank = load_real_choice()
    print('抓取模拟题…')
    sim = load_sim()
    print('抓取背诵卡…')
    cards = load_cards()

    if args.demo:
        bank, sim = bank[:args.demo], sim[:max(1, args.demo // 4)]
        cards = [c for c in cards if c['back'] and len(c['back']) >= 30][:args.demo]

    data = {'bank': bank, 'sim': sim, 'cards': cards}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(out) / 1024
    print(f"\n完成：真题 {len(bank)} / 模拟 {len(sim)} / 卡片 {len(cards)}，"
          f"写入 {out}（{size:.0f} KB）")


if __name__ == '__main__':
    main()
