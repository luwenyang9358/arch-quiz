#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把论文范文 PDF 转成背诵卡（k='pf', year='论文范文'）。

前置：需要一个能把 PDF 抽成纯文本的小工具（任意 PDF 文本抽取器均可），
本仓库默认调用外部的 `pdftext`：

    python3 tools/parse_essay_pdf.py --pdf-dir ~/Downloads/lunwen --out app/data/cards_extra.json

处理要点
--------
* 范文 PDF 常带水印/页眉页脚（题库平台名、公众号、页码），先按规则行过滤掉；
* PDF 的硬换行会把一句话切成多行，需要按标点合并成段落，否则卡片上逐行短句很难读；
* 章节标记既有「摘要：」也有「摘要:」，且有「有摘要无正文」的情况，两种都要兜住；
* 提纲笔记类文档（含「我的范文」）不是范文，直接跳过。
"""
import argparse
import glob
import json
import os
import re
import subprocess

WATER = [
    re.compile(r'手机端题库：微信搜索「软考达人」.*?ruankaodaren\.com'),
    re.compile(r'软考达人：软考专业备考平台.*'),
    re.compile(r'关注「?CTO说」?.*'),
    re.compile(r'微信搜索「?软考达人」?.*'),
]
SECTION = re.compile(r'^(摘\s*要|正文|关键词|Abstract)\s*[:：]?\s*')
JUNK = re.compile(r'^(PAGES\s*\d+|我的范文|历年真题|试\s*题[一二三四五])$')


def pdf_text(path, exe='pdftext'):
    r = subprocess.run([exe, path], capture_output=True)
    s = r.stdout.decode('utf-8', 'replace')
    s = re.sub(r'^PAGES \d+\s*', '', s)
    lines = []
    for ln in s.split('\n'):
        if re.match(r'^===\s*page\s*\d+\s*===', ln):
            continue
        t = ln.strip()
        if not t:
            continue
        empty = False
        for w in WATER:
            if w.search(t):
                t = w.sub('', t).strip()
                empty = not t
        if not empty and t:
            lines.append(t)
    return lines


def build_body(lines):
    """按标点合并硬换行成段落，章节标记单独成行"""
    out, buf = [], ''
    for t in lines:
        if JUNK.match(t):
            continue
        sm = SECTION.match(t)
        if sm:
            if buf:
                out.append(buf)
                buf = ''
            out.append('### ' + re.sub(r'\s+', '', sm.group(1)))
            t = t[sm.end():].strip()
            if not t:
                continue
        if re.match(r'^（\d{1,2}）', t) or re.match(r'^\d{1,2}[．\.、]', t) \
           or re.match(r'^(首先|其次|再次|最后|总之|综上所述|第一|第二|第三)', t):
            if buf:
                out.append(buf)
                buf = ''
        if buf and not re.search(r'[。！？：；”』]$', buf):
            buf += t
        else:
            if buf:
                out.append(buf)
            buf = t
    if buf:
        out.append(buf)
    # 段落定长切分，避免出现过长的巨段
    res = []
    for p in out:
        if p.startswith('###'):
            res.append(p)
        else:
            res.extend(p[i:i + 260] for i in range(0, len(p), 260))
    return '\n\n'.join(res)


def title_of(fn, lines):
    base = os.path.basename(fn)[:-4]
    for t in lines[:6]:
        if t.startswith('论') and 4 <= len(t) <= 40:
            return t.replace(' ', '')
    return re.sub(r'（.*?）|【.*?】|-来源于.*', '', base).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf-dir', required=True)
    ap.add_argument('--out', default='app/data/cards_extra.json')
    ap.add_argument('--pdftext', default='pdftext', help='PDF 文本抽取可执行文件')
    args = ap.parse_args()

    cards = []
    for f in sorted(glob.glob(os.path.join(args.pdf_dir, '*.pdf'))):
        lines = pdf_text(f, args.pdftext)
        if len(''.join(lines)) < 400:
            print('  跳过(内容过少) %s' % os.path.basename(f))
            continue
        if any(k in os.path.basename(f) for k in ('模板', '技巧')) or '我的范文' in ''.join(lines):
            print('  跳过(非范文) %s' % os.path.basename(f))
            continue
        body = build_body(lines)
        title = title_of(f, lines)
        m = re.search(r'### 摘要(.*?)(?=### 正文|$)', body, re.S)
        m2 = re.search(r'### 正文(.*)$', body, re.S)
        zhaiyao = re.sub(r'\s+', '', m.group(1)) if m else ''
        zhengwen = (m2.group(1) if m2 else body).strip()
        if len(zhengwen) < 500:
            print('  跳过(正文过短) %s' % os.path.basename(f))
            continue
        hook = (zhaiyao or re.sub(r'[#\s]', '', zhengwen))[:110]
        words = len(re.sub(r'\n', '', zhengwen))
        cards.append({
            'title': title, 'back': body, 'k': 'pf', 'year': '论文范文',
            'no': len(cards) + 1, 'id': 'pf-范文扩充-%d' % (len(cards) + 1),
            'front': (f'{title}\n\n【真题范文 · 背诵用】\n\n摘要开头：\n“{hook}……”\n\n'
                      f'请复述：① 项目背景与我的角色　② 采用的技术方案与架构设计　'
                      f'③ 实施效果与经验总结\n\n（正文约 {words} 字）'),
        })
        print('  %s  摘要 %d 字 / 正文 %d 字' % (title, len(zhaiyao), words))

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    json.dump(cards, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('生成范文卡 %d 张 → %s' % (len(cards), args.out))


if __name__ == '__main__':
    main()
