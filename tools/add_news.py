"""お知らせを news.md に1行足す（Claudeのチャットからお知らせを足すとき用）

使い方：  py -3 tools/add_news.py "お知らせの文" [--date 2026-11-20]

・日付を付けなければ今日の日付
・説明の下（いちばん上）に足す。同じ行がすでにあれば足さない
・URLを文に含めるとボタン・動画になる（くわしくは news.md の説明）
・足すだけです。公開（git push）は、たぬのOKをもらってから別にやります
"""
import datetime as dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'news.md')


def main(argv):
    date = dt.date.today().isoformat()
    if '--date' in argv:
        i = argv.index('--date')
        date = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            sys.exit('日付は 2026-11-20 の形で書いてください')
    text = ' '.join(argv).strip()
    if not text:
        sys.exit(__doc__)
    if '\n' in text:
        sys.exit('お知らせは1行で書いてください')
    line = f'{date} {text}'

    raw = open(PATH, 'rb').read()
    crlf = b'\r\n' in raw
    lines = raw.decode('utf-8').replace('\r\n', '\n').split('\n')
    if line in lines:
        print('同じお知らせがすでにあります：', line)
        return
    # 「# から始まる説明」のすぐ下に入れる
    at = 0
    for i, l in enumerate(lines):
        if l.startswith('#'):
            at = i + 1
    while at < len(lines) and lines[at].strip() == '':
        at += 1
    lines.insert(at, line)
    out = '\n'.join(lines)
    if crlf:
        out = out.replace('\n', '\r\n')
    open(PATH, 'wb').write(out.encode('utf-8'))
    print('足しました：', line)


if __name__ == '__main__':
    main(sys.argv[1:])
