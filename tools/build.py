# -*- coding: utf-8 -*-
"""
バンドのホームページを作る（GitHubが自動で動かす。人は触らなくてよい）。

  python tools/build.py                  -> _site/ に公開用のページ
  python tools/build.py --preview        -> _site/preview.html も作る（色と字を試すパネル付き）
  python tools/build.py --ics FILE       -> カレンダーをファイルから読む（試し用）
  python tools/build.py --mihon          -> _mihon/ に「見本」1ファイル（画像も中に入っていて、ダウンロードして開ける）

入力:
  settings.toml   名前・色・リンク・メンバー
  about.md        バンド紹介の文章
  photos/         写真（ここに置いた分を新しい順に並べる。軽くして位置情報も消して載せる）
  flyers/         フライヤー（2026-12-12.jpg のように日付の名前にすると、その日の予定に付く）
  schedule/       スケジュール一覧の画像（Canvaで作ったもの）
  shop.md         グッズ（1行に1つ。名前 | 値段 | 商品ページのURL | 画像）
  環境変数 CAL_ICS_URL   Googleカレンダーの「iCal形式の非公開URL」（GitHubの鍵付きの場所に入れておく）

ライブ予定に出すのは：今日以降・hide の言葉が入っていない予定だけ。
説明欄は、開場・開演・料金・チケット・出演 の行だけ出す（タグや内部のメモは出さない）。
"""
import base64
import calendar
import datetime as dt
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.parse
import urllib.request

from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, '_site')
JST = dt.timezone(dt.timedelta(hours=9))
IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp')
WEEK = '月火水木金土日'

# 見出しの字: key -> (CSSの名前, Google Fontsの指定, パネルの表示名)
FONTS = {
    'noto': ('"Noto Sans JP"', 'Noto+Sans+JP:wght@700;900', 'ふつうのゴシック'),
    'dela': ('"Dela Gothic One"', 'Dela+Gothic+One', 'デラゴシック（太い）'),
    'rocknroll': ('"RocknRoll One"', 'RocknRoll+One', 'ロックンロール'),
    'rounded': ('"M PLUS Rounded 1c"', 'M+PLUS+Rounded+1c:wght@800', 'まるゴシック'),
    'mochiy': ('"Mochiy Pop One"', 'Mochiy+Pop+One', 'もちポップ（まるい）'),
    'zenmaru': ('"Zen Maru Gothic"', 'Zen+Maru+Gothic:wght@900', 'ゼンまるゴシック'),
    'kiwi': ('"Kiwi Maru"', 'Kiwi+Maru:wght@500', 'キウイまる（やさしい）'),
    'hachimaru': ('"Hachi Maru Pop"', 'Hachi+Maru+Pop', 'はちまるポップ（丸文字）'),
    'darumadrop': ('"Darumadrop One"', 'Darumadrop+One', 'だるまドロップ（ぷっくり）'),
    'potta': ('"Potta One"', 'Potta+One', 'ポッタ（筆の太字）'),
    'reggae': ('"Reggae One"', 'Reggae+One', 'レゲエ（かすれ太字）'),
    'monomaniac': ('"Monomaniac One"', 'Monomaniac+One', 'モノマニアック（角ばり）'),
    'train': ('"Train One"', 'Train+One', 'トレイン（二重線）'),
    'rampart': ('"Rampart One"', 'Rampart+One', 'ランパート（立体）'),
    'dot': ('"DotGothic16"', 'DotGothic16', 'ドット（ゲーム風）'),
    'stick': ('"Stick"', 'Stick', 'スティック（細長い）'),
    'yusei': ('"Yusei Magic"', 'Yusei+Magic', 'マジック書き'),
    'slackside': ('"Slackside One"', 'Slackside+One', 'ペン書き（ゆるい）'),
    'klee': ('"Klee One"', 'Klee+One:wght@600', 'クレー（えんぴつ）'),
    'kaisei': ('"Kaisei Decol"', 'Kaisei+Decol:wght@700', 'カイセイ（レトロ明朝）'),
    'shippori': ('"Shippori Mincho B1"', 'Shippori+Mincho+B1:wght@800', 'しっぽり明朝'),
    'yuji': ('"Yuji Syuku"', 'Yuji+Syuku', '毛筆'),
}
# 説明欄から出してよい行
SHOW_LINE = re.compile(r'^(開場|開演|OPEN|START|料金|チケット|前売|当日|出演|共演)', re.I)
LEAD_EMOJI = re.compile('^[\U0001F000-\U0001FAFF☀-➿️‍\\s]+')


def esc(s):
    return html.escape(str(s or ''), quote=True)


# ---------------- カレンダー ----------------

def unesc(v):
    return re.sub(r'\\(.)', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), v)


def parse_ics(text):
    lines = []
    for ln in text.replace('\r\n', '\n').split('\n'):
        if ln[:1] in (' ', '\t') and lines:
            lines[-1] += ln[1:]
        else:
            lines.append(ln)
    evs, cur = [], None
    for ln in lines:
        if ln == 'BEGIN:VEVENT':
            cur = {}
        elif ln == 'END:VEVENT' and cur is not None:
            evs.append(cur)
            cur = None
        elif cur is not None and ':' in ln:
            k, v = ln.split(':', 1)
            name, *params = k.split(';')
            cur.setdefault(name, (v, params))
    return evs


def ics_when(val):
    """DTSTART -> ('2026-12-12', '19:00' か None)"""
    v, params = val
    if 'VALUE=DATE' in params or len(v) == 8:
        return '%s-%s-%s' % (v[:4], v[4:6], v[6:8]), None
    t = dt.datetime.strptime(v[:15], '%Y%m%dT%H%M%S')
    if v.endswith('Z'):
        t = t.replace(tzinfo=dt.timezone.utc).astimezone(JST)
    return t.strftime('%Y-%m-%d'), t.strftime('%H:%M')


def live_events(ics_text, hide, today):
    out = []
    for e in parse_ics(ics_text):
        if 'DTSTART' not in e or e.get('STATUS', ('',))[0] == 'CANCELLED' or 'RECURRENCE-ID' in e:
            continue
        summary = unesc(e.get('SUMMARY', ('', []))[0]).strip()
        desc = unesc(e.get('DESCRIPTION', ('', []))[0])
        if any(w and (w in summary or w in desc) for w in hide):
            continue
        date, time = ics_when(e['DTSTART'])
        if date < today:
            continue
        title = LEAD_EMOJI.sub('', summary)
        venue = ''
        m = re.match(r'^(.*?)\s*[＠@]\s*(.+)$', title)
        if m:
            title, venue = m.group(1), m.group(2)
        loc = unesc(e.get('LOCATION', ('', []))[0]).strip()
        if not venue:
            venue = re.split(r'[（(]', loc)[0].strip()
        info = [ln.strip() for ln in desc.split('\n')
                if SHOW_LINE.match(ln.strip()) and not any(w and w in ln for w in hide)]
        if time and not any(re.match('(開場|開演|OPEN|START)', x, re.I) for x in info):
            info.insert(0, '%s〜' % time)
        y, mo, d = map(int, date.split('-'))
        out.append({'id': date.replace('-', '') + (time or '').replace(':', ''), 'date': date, 'm': mo, 'd': d,
                    'dow': WEEK[dt.date(y, mo, d).weekday()], 'title': title, 'venue': venue, 'info': info, 'flyer': '',
                    'map': re.sub(r'[（）()]', ' ', loc).strip() or venue})
    out.sort(key=lambda x: x['id'])
    return out


def ics_url(raw):
    """鍵付きの場所に入れたカレンダーのURLを読める形にそろえる（前後の空白・引用符、webcal://、https:// の付け忘れ）"""
    u = raw.strip().strip('"\'<>').strip()
    if u.lower().startswith('webcal://'):
        u = 'https://' + u[len('webcal://'):]
    elif u.lower().startswith(('calendar.google.com/', 'www.google.com/calendar/')):
        u = 'https://' + u
    return u


def url_shape(u):
    """URLそのものは出さずに、形だけを書く（自動更新の記録はだれでも読めるため）"""
    yn = lambda b: 'はい' if b else 'いいえ'
    return (f'長さ{len(u)}文字／https://で始まる：{yn(u.lower().startswith("https://"))}'
            f'／「@」がある：{yn("@" in u)}／「/」がある：{yn("/" in u)}／.icsで終わる：{yn(u.lower().endswith(".ics"))}')


def load_ics(argv):
    if '--ics' in argv:
        with open(argv[argv.index('--ics') + 1], encoding='utf-8') as f:
            return f.read()
    url = ics_url(os.environ.get('CAL_ICS_URL', ''))
    if not url:
        print('（カレンダーのURLが無いので、ライブ予定は空で作ります）')
        return ''
    if not url.lower().startswith(('https://', 'http://')):
        sys.exit('カレンダーのURL（CAL_ICS_URL）がURLの形になっていません。'
                 'Googleカレンダーの「iCal形式の非公開アドレス」（https://calendar.google.com/calendar/ical/…/basic.ics）を入れてください。'
                 '（いま入っているものの形：' + url_shape(url) + '）')
    req = urllib.request.Request(url, headers={'User-Agent': 'band-site-builder'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')


# ---------------- 写真 ----------------

def git_time(path):
    try:
        out = subprocess.run(['git', 'log', '-1', '--format=%ct', '--', path], cwd=ROOT,
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return int(out or 0)
    except Exception:
        return 0


def shrink(src, dst, size):
    """長い辺を size に。向きを直し、位置情報などの付帯情報は付けずにJPEGで保存"""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size))
        if im.mode not in ('RGB', 'L'):
            bg = Image.new('RGB', im.size, (255, 255, 255))
            bg.paste(im.convert('RGBA'), mask=im.convert('RGBA').split()[-1])
            im = bg
        im.save(dst, 'JPEG', quality=82, optimize=True, progressive=True)


def images(folder):
    d = os.path.join(ROOT, folder)
    if not os.path.isdir(d):
        return []
    files = [f for f in os.listdir(d) if f.lower().endswith(IMG_EXT)]
    return sorted(files, key=lambda f: (git_time(os.path.join(folder, f)), f), reverse=True)


def safe_name(f):
    stem = os.path.splitext(f)[0]
    return re.sub(r'[^0-9A-Za-z_.-]+', '_', stem).strip('_') or 'photo'


def build_photos():
    out = []
    for f in images('photos'):
        n = safe_name(f)
        try:
            shrink(os.path.join(ROOT, 'photos', f), os.path.join(OUT, 'photos', n + '.jpg'), 1600)
            shrink(os.path.join(ROOT, 'photos', f), os.path.join(OUT, 'photos', 's', n + '.jpg'), 640)
            out.append(n)
        except Exception as e:
            print('写真を読めませんでした:', f, e)
    return out


def build_schedule():
    """schedule/ に置いたスケジュール一覧の画像（Canvaで作ったもの）。名前の順"""
    d = os.path.join(ROOT, 'schedule')
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(IMG_EXT)) if os.path.isdir(d) else []
    out = []
    for f in files:
        n = safe_name(f)
        try:
            shrink(os.path.join(d, f), os.path.join(OUT, 'schedule', n + '.jpg'), 1600)
            out.append('schedule/%s.jpg' % n)
        except Exception as e:
            print('一覧の画像を読めませんでした:', f, e)
    return out


def ichiran_html(paths):
    """ライブ予定のいちばん上に出す一覧の画像（2枚以上なら横にスワイプ）"""
    if not paths:
        return ''
    items = ''.join('<a class="js-zoom" href="%s"><img src="%s" alt="スケジュール一覧" loading="lazy"></a>' % (p, p) for p in paths)
    return ('<div class="ichiran-top"><div class="ichiran%s">%s</div><p class="muted ichiran-note">タップで大きく見られます</p></div>'
            % (' many' if len(paths) > 1 else '', items))


def reel_html(paths, events):
    """たぬら式：一覧の画像とフライヤーを横に並べた帯（◀ ながす ▶）"""
    slides = ['<figure class="slide"><a class="js-zoom" href="%s"><img src="%s" alt="スケジュール一覧" loading="lazy"></a>'
              '<figcaption>📰 スケジュール一覧（タップで大きく）</figcaption></figure>' % (p, p) for p in paths]
    slides += ['<figure class="slide"><a class="js-zoom" href="%s"><img src="%s" alt="%s のフライヤー" loading="lazy"></a>'
               '<figcaption>%d/%d(%s) %s</figcaption></figure>'
               % (esc(e['flyer']), esc(e['flyer']), esc(e['title']), e['m'], e['d'], esc(e['dow']), esc(e['title']))
               for e in events if e['flyer']]
    if not slides:
        return '<p class="muted">一覧とフライヤーはまだありません。</p>'
    return ('<div class="reel-wrap"><div class="reel" id="reel" tabindex="0" aria-label="スケジュール一覧とフライヤー">%s</div>'
            '<div class="reel-ctrl"><button type="button" id="reel-prev" aria-label="前へ">◀</button>'
            '<button type="button" id="reel-play">▶ ながす</button>'
            '<button type="button" id="reel-next" aria-label="次へ">▶</button></div>'
            '<div class="dots" id="reel-dots">%s</div></div>' % (''.join(slides), '<i></i>' * len(slides)))


def remote_flyers(site, unit):
    """松たぬら情報サイト（公開ページ）に出ているフライヤーを {日付: 画像URL} で返す。
    あちらは解禁済みの予定しか出さないので、まだ言えないフライヤーは来ない。読めなければ空。"""
    if not site or not unit:
        return {}
    try:
        req = urllib.request.Request(site.rstrip('/') + '/', headers={'User-Agent': 'band-site-builder'})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode('utf-8')
        m = re.search(r'<script type="application/json" id="cal-data">(.*?)</script>', page, re.S)
        out = {}
        for e in json.loads(m.group(1)) if m else []:
            if e.get('unit') == unit and str(e.get('flyer', '')).startswith('https://'):
                out.setdefault(e.get('date', ''), e['flyer'])
        print('（フライヤー：たぬらサイトから %d 枚）' % len(out))
        return out
    except Exception as ex:
        print('（フライヤー：たぬらサイトを読めず → フォルダの分だけ：%s）' % str(ex)[:80])
        return {}


def attach_flyers(events, live):
    """flyers/ フォルダに日付の名前で置いた画像が優先。無ければたぬらサイトのフライヤー"""
    by_date = {}
    for f in images('flyers'):
        m = re.match(r'(\d{4})-?(\d{2})-?(\d{2})', f)
        if m:
            by_date.setdefault('%s-%s-%s' % m.groups(), f)
    remote = remote_flyers(live.get('flyers_from', ''), live.get('flyers_unit', ''))
    for ev in events:
        f = by_date.get(ev['date'])
        if f:
            n = safe_name(f)
            shrink(os.path.join(ROOT, 'flyers', f), os.path.join(OUT, 'flyers', n + '.jpg'), 1600)
            ev['flyer'] = 'flyers/%s.jpg' % n
        elif remote.get(ev['date']):
            url, dst = remote[ev['date']], os.path.join(OUT, 'flyers', ev['date'] + '.jpg')
            try:   # 取ってきて軽くして自分のページに置く（だめならあちらの画像をそのまま表示）
                req = urllib.request.Request(url, headers={'User-Agent': 'band-site-builder'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                tmp = dst + '.src'
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(tmp, 'wb') as w:
                    w.write(data)
                shrink(tmp, dst, 1600)
                os.remove(tmp)
                ev['flyer'] = 'flyers/%s.jpg' % ev['date']
            except Exception:
                ev['flyer'] = url


# ---------------- ページの部品 ----------------

def ig_url(h):
    return h if h.startswith('http') else 'https://www.instagram.com/%s/' % h.lstrip('@')


def x_url(h):
    return h if h.startswith('http') else 'https://x.com/%s' % h.lstrip('@')


def th_url(h):
    return h if h.startswith('http') else 'https://www.threads.net/@%s' % h.lstrip('@')


def link_row(d):
    pairs = [('instagram', 'Instagram', ig_url), ('x', 'X', x_url), ('threads', 'Threads', th_url),
             ('youtube', 'YouTube', None), ('facebook', 'Facebook', None)]
    return ''.join('<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(fn(d[k]) if fn else d[k]), label)
                   for k, label, fn in pairs if d.get(k))


def ev_html(ev, rv, later=False):
    info = ''.join('<li>%s</li>' % esc(x) for x in ev['info'])
    mp = ('<a class="ev-map" href="https://www.google.com/maps/search/?api=1&amp;query=%s" target="_blank" rel="noopener">地図</a>'
          % urllib.parse.quote(ev['map'])) if ev.get('map') else ''
    venue = '<p class="ev-venue">%s%s</p>' % (esc(ev['venue']), mp) if ev['venue'] else ''
    flyer = ('<a class="ev-flyer js-zoom" href="%s" data-ev="%s"><img src="%s" alt="%s のフライヤー" loading="lazy"></a>'
             % (esc(ev['flyer']), esc(ev['id']), esc(ev['flyer']), esc(ev['title']))) if ev['flyer'] else ''
    btn = '<a class="rv-btn" href="#sec-reserve" data-rv="%s">予約する</a>' % esc(ev['id']) if rv else ''
    return ('<article class="ev%s"><div class="ev-date"><span class="ev-m">%d月</span><span class="ev-d">%d</span>'
            '<span class="ev-w">%s</span></div><div class="ev-body"><h3>%s</h3>%s<ul class="ev-info">%s</ul>%s</div>%s</article>'
            % (' later' if later else '', ev['m'], ev['d'], esc(ev['dow']), esc(ev['title']), venue, info, btn, flyer))


def list_html(events, rv, today, live):
    """リスト：○か月先まで（少なくても○件）を出して、残りは「さらに見る」でひらく"""
    if not events:
        return '<p class="muted">いまは予定がありません。</p>'
    months, least = int(live.get('list_months', 2)), int(live.get('list_min', 3))
    y, m = divmod(today.month - 1 + months, 12)
    y, m = today.year + y, m + 1
    limit = dt.date(y, m, min(today.day, calendar.monthrange(y, m)[1])).isoformat()
    n = max(sum(1 for e in events if e['date'] <= limit), min(least, len(events)))
    h = '<div class="evlist" id="evlist">%s</div>' % ''.join(ev_html(e, rv, i >= n) for i, e in enumerate(events))
    if len(events) > n:
        h += '<button type="button" class="more-btn" id="ev-more">さらに見る（%d件）</button>' % (len(events) - n)
    return h


def channel_id(v, links):
    """チャンネルID（UC…）。settings に無ければ YouTube のチャンネルページから探す"""
    cid = v.get('channel_id', '').strip()
    if cid or not links.get('youtube'):
        return cid
    try:
        req = urllib.request.Request(links['youtube'], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            m = re.search(r'"externalId":"(UC[\w-]{22})"', r.read().decode('utf-8', 'replace'))
        return m.group(1) if m else ''
    except Exception:
        return ''


def video_html(v, links):
    """再生リストのURLがあればそれ。無ければチャンネルの動画を新しい順に（あげた動画が自動で先頭に来る）"""
    m = re.search(r'[?&]list=([\w-]+)', v.get('playlist', ''))
    lst = m.group(1) if m else ''
    if not lst:
        cid = channel_id(v, links)
        lst = ('UU' + cid[2:]) if cid.startswith('UC') else ''
    body = ('<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/videoseries?list=%s" '
            'title="YouTube の動画" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>' % esc(lst)) if lst else ''
    if links.get('youtube'):
        body += '<p><a class="more" href="%s" target="_blank" rel="noopener">YouTubeチャンネルを見る →</a></p>' % esc(links['youtube'])
    return body or '<p class="muted">動画はこれから。</p>'


# ---------------- グッズ ----------------

def shop_image(src, i):
    """商品の画像：shop フォルダのファイルか画像のURL。軽くして自分のページに置く（URLが読めなければそのまま表示）"""
    if not src:
        return ''
    dst = os.path.join(OUT, 'shop', '%02d.jpg' % i)
    try:
        if src.startswith('http'):
            req = urllib.request.Request(src, headers={'User-Agent': 'band-site-builder'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst + '.src', 'wb') as w:
                w.write(data)
            shrink(dst + '.src', dst, 600)
            os.remove(dst + '.src')
        else:
            shrink(os.path.join(ROOT, 'shop', src), dst, 600)
        return 'shop/%02d.jpg' % i
    except Exception as e:
        print('グッズの画像を読めませんでした:', src[:60], e)
        return src if src.startswith('http') else ''


def load_shop():
    """shop.md：1行に1つ「名前 | 値段 | 商品ページのURL | 画像」"""
    p = os.path.join(ROOT, 'shop.md')
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith('#'):
                continue
            parts = [x.strip() for x in re.split(r'[|｜]', ln)]
            if len(parts) < 3 or not parts[2].startswith('http'):
                print('グッズの行を読めませんでした:', ln[:40])
                continue
            out.append({'name': parts[0], 'price': parts[1], 'url': parts[2],
                        'img': shop_image(parts[3] if len(parts) > 3 else '', len(out))})
    return out


def goods_html(items, flow_min, shop=None):
    """商品のカード。flow_min 個以上あると、横にゆっくり流れる（さわると止まる）。
    お店のURLがあれば、お店の名前の見出しを付けた枠（埋め込みのような箱）に入れる"""
    if not items:
        return ''
    shop = shop or {}
    head = ('<a class="shopbox-head" href="%s" target="_blank" rel="noopener"><span>🛒 %s</span><span>お店を見る →</span></a>'
            % (esc(shop['url']), esc(shop.get('name') or 'ショップ'))) if shop.get('url') else ''

    def card(it, hidden=False):
        img = '<img src="%s" alt="" loading="lazy">' % esc(it['img']) if it['img'] else '<span class="g-noimg">♪</span>'
        return ('<a class="good" href="%s" target="_blank" rel="noopener"%s>%s<span class="g-name">%s</span><span class="g-price">%s</span></a>'
                % (esc(it['url']), ' aria-hidden="true" tabindex="-1"' if hidden else '', img, esc(it['name']), esc(it['price'])))
    cards = ''.join(card(x) for x in items)
    if len(items) >= flow_min:
        body = ('<div class="goods flow" style="--n:%d"><div class="goods-in">%s%s</div></div>'
                % (len(items), cards, ''.join(card(x, True) for x in items)))
    else:
        body = '<div class="goods%s"><div class="goods-in">%s</div></div>' % (' one' if len(items) == 1 else '', cards)
    return '<div class="shopbox">%s%s</div>' % (head, body) if head else body


# ---------------- お知らせ ----------------

NEWS_LINE = re.compile(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})[\s　]+(.+)$')
URL_RE = re.compile(r'https?://[^\s　]+')
NEWS_SHOW, NEWS_VIDEOS, NEWS_NEW_DAYS = 5, 3, 14


def youtube_id(url):
    m = re.search(r'(?:youtu\.be/|[?&]v=|/shorts/|/live/|/embed/)([\w-]{11})', url)
    return m.group(1) if m else ''


def url_label(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    for key, label in (('youtu', '▶ YouTubeで見る'), ('instagram', 'Instagramで見る'),
                       ('threads', 'Threadsで見る'), ('x.com', 'Xで見る'), ('twitter', 'Xで見る'),
                       ('facebook', 'Facebookで見る'), ('tiktok', 'TikTokで見る')):
        if key in host:
            return label
    return 'くわしく見る'


def load_news():
    p = os.path.join(ROOT, 'news.md')
    if not os.path.exists(p):
        return []
    items = []
    with open(p, encoding='utf-8') as f:
        for ln in f:
            m = NEWS_LINE.match(ln.strip())
            if not m:
                continue
            try:
                d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            text = m.group(4)
            urls = URL_RE.findall(text)
            items.append({'date': d, 'text': URL_RE.sub('', text).strip(), 'urls': urls})
    items.sort(key=lambda x: x['date'], reverse=True)
    return items


def news_item(it, i, today):
    new = (today - it['date']).days <= NEWS_NEW_DAYS
    vid = next((youtube_id(u) for u in it['urls'] if youtube_id(u)), '') if i < NEWS_VIDEOS else ''
    h = '<li class="nw"><p class="nw-head"><time datetime="%s">%d.%d.%d</time>%s</p>' % (
        it['date'].isoformat(), it['date'].year, it['date'].month, it['date'].day,
        '<span class="new">NEW</span>' if new else '')
    if it['text']:
        h += '<p class="nw-text">%s</p>' % esc(it['text'])
    if vid:
        h += ('<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/%s" title="YouTube 動画" '
              'loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>' % vid)
    links = [u for u in it['urls'] if not (vid and youtube_id(u) == vid)]
    if links:
        h += '<p class="nw-links">%s</p>' % ''.join(
            '<a class="more" href="%s" target="_blank" rel="noopener">%s →</a>' % (esc(u), url_label(u)) for u in links)
    return h + '</li>'


def news_html(items, today):
    if not items:
        return '<p class="muted">いまはお知らせがありません。</p>'
    rows = [news_item(it, i, today) for i, it in enumerate(items)]
    h = '<ul class="news">%s</ul>' % ''.join(rows[:NEWS_SHOW])
    if len(rows) > NEWS_SHOW:
        h += '<details class="news-more"><summary>前のお知らせ（%d件）</summary><ul class="news">%s</ul></details>' % (
            len(rows) - NEWS_SHOW, ''.join(rows[NEWS_SHOW:]))
    return h


def members_html(ms):
    cards = []
    for mb in ms:
        links = ''.join(x for x in [
            '<a href="%s" target="_blank" rel="noopener">Instagram</a>' % esc(ig_url(mb['instagram'])) if mb.get('instagram') else '',
            '<a href="%s" target="_blank" rel="noopener">X</a>' % esc(x_url(mb['x'])) if mb.get('x') else ''])
        text = '<p>%s</p>' % esc(mb['text']) if mb.get('text') else ''
        cards.append('<article class="member"><h3>%s<small>%s</small></h3>%s<div class="links">%s</div></article>'
                     % (esc(mb.get('name')), esc(mb.get('part')), text, links))
    return ''.join(cards)


def video_card(m):
    """見本用：ファイルで開くとYouTubeは埋め込めないので、YouTubeへのリンクにする"""
    src = html.unescape(m.group(1))
    lst = re.search(r'list=([\w-]+)', src)
    vid = None if lst else re.search(r'/embed/([\w-]{11})(?:[?&#]|$)', src)
    url = ('https://www.youtube.com/playlist?list=' + lst.group(1)) if lst else ('https://www.youtube.com/watch?v=' + vid.group(1)) if vid else src
    thumb = '<img src="https://i.ytimg.com/vi/%s/hqdefault.jpg" alt="">' % vid.group(1) if vid else ''
    return ('<a class="video-card" href="%s" target="_blank" rel="noopener">%s<b>▶ YouTubeで見る</b>'
            '<small>本番のページでは、ここで動画がそのまま再生できます</small></a>' % (esc(url), thumb))


def inline_assets(page):
    """見本用：ページの画像を全部ファイルの中に入れる（ダウンロードして1つで見られるように）"""
    cache = {}

    def data_uri(rel):
        if rel not in cache:
            p = os.path.join(OUT, rel.replace('/', os.sep))
            if not os.path.exists(p):
                cache[rel] = rel
            elif rel.endswith('.svg'):
                with open(p, 'rb') as f:
                    cache[rel] = 'data:image/svg+xml;base64,' + base64.b64encode(f.read()).decode()
            else:
                with Image.open(p) as im:
                    im = im.convert('RGB')
                    im.thumbnail((1000, 1000))
                    buf = io.BytesIO()
                    im.save(buf, 'JPEG', quality=72, optimize=True)
                cache[rel] = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
        return cache[rel]
    page = re.sub(r'<div class="video"><iframe src="([^"]+)"[^>]*></iframe></div>', video_card, page)
    return re.sub(r'(src|href)="((?:assets|photos|flyers|schedule|shop)/[^"#?]+)"',
                  lambda m: '%s="%s"' % (m.group(1), data_uri(m.group(2))), page)


def on_color(hex_):
    """差し色の上に乗せる字の色（明るい色なら黒・暗い色なら白）"""
    h = hex_.lstrip('#')
    if len(h) != 6:
        return '#ffffff'
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return '#111111' if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6 else '#ffffff'


def card_color(ink):
    """カードの面の色（文字が暗い色なら白、文字が明るい色なら背景を少しだけ文字の色に寄せる）"""
    if on_color(ink) == '#ffffff':
        return '#ffffff'
    return 'color-mix(in srgb,var(--ink) 8%,var(--bg))'


def about_html(text):
    """紹介文：最初の段落（空行まで）だけ見せ、残りは「続きを読む」でたたむ"""
    head, _, rest = text.partition('\n\n')
    h = esc(head.strip()).replace('\n', '<br>')
    rest = rest.strip()
    if not rest:
        return h
    r = esc(rest).replace('\n\n', '</p><p>').replace('\n', '<br>')
    return h + '<details class="about-more"><summary>続きを読む</summary><p>' + r + '</p></details>'


def build(preview=False, argv=(), mihon=False):
    with open(os.path.join(ROOT, 'settings.toml'), 'rb') as f:
        S = tomllib.load(f)
    about = ''
    if os.path.exists(os.path.join(ROOT, 'about.md')):
        with open(os.path.join(ROOT, 'about.md'), encoding='utf-8') as f:
            about = f.read().strip()
    look, links, live, contact = S.get('look', {}), S.get('links', {}), S.get('live', {}), S.get('contact', {})
    now = dt.datetime.now(JST)

    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, 'assets'), os.path.join(OUT, 'assets'))
    photos = build_photos()
    events = live_events(load_ics(list(argv)), live.get('hide', []), now.strftime('%Y-%m-%d'))
    attach_flyers(events, live)
    rv = bool(live.get('reserve_dm'))

    font = look.get('font', 'noto')
    font_css, _, _ = FONTS.get(font, FONTS['noto'])
    font_url = lambda keys: 'https://fonts.googleapis.com/css2?%s&display=swap' % '&'.join(
        'family=' + x for x in sorted({FONTS[k][1] for k in keys}))
    nxt = events[0] if events else None
    ticker = ('NEXT → %d/%d(%s) %s%s' % (nxt['m'], nxt['d'], nxt['dow'], nxt['title'], '＠' + nxt['venue'] if nxt['venue'] else '')
              if nxt else S.get('tagline', ''))
    sched = build_schedule()
    goods = goods_html(load_shop(), int(S.get('shop', {}).get('flow_min', 3)), S.get('shop', {}))
    # 公開のリポジトリに書かなくてすむよう、GitHubの鍵付きの場所 CONTACT_MAIL があればそちらを使う
    mail = (os.environ.get('CONTACT_MAIL', '').strip() or contact.get('mail', '')).strip()
    photo_html = ''.join('<a class="js-photo" href="photos/%s.jpg" target="_blank" rel="noopener"><img src="photos/s/%s.jpg" alt="" loading="lazy"></a>'
                         % (n, n) for n in photos) or '<p class="muted">写真はこれから。</p>'

    with open(os.path.join(ROOT, 'tools', 'template.html'), encoding='utf-8') as f:
        page = f.read()
    logo = ''
    if os.path.exists(os.path.join(ROOT, 'assets', 'logo.svg')):
        with open(os.path.join(ROOT, 'assets', 'logo.svg'), encoding='utf-8') as f:
            svg = f.read()
        logo = re.sub(r'<svg\b', '<svg class="logo" role="img" aria-label="%s のロゴ"' % esc(S.get('name')), svg[svg.index('<svg'):], count=1)
    rep = {
        'LOGO': logo,
        'NAME': esc(S.get('name')), 'NAME_EN': esc(S.get('name_en')), 'TAGLINE': esc(S.get('tagline')),
        'URL': esc(S.get('url', '').rstrip('/')),
        'ABOUT': about_html(about),
        'BG': esc(look.get('background', '#ffffff')), 'INK': esc(look.get('text', '#111111')),
        'ACCENT': esc(look.get('accent', '#111111')), 'ON_ACCENT': on_color(look.get('accent', '#111111')),
        'CARD': card_color(look.get('text', '#111111')),
        'HEAD': font_css, 'FONT_KEY': esc(font),
        'TICKER': esc(ticker),
        'NEXT': ev_html(nxt, rv) if nxt else '<p class="muted">次のライブは準備中。</p>',
        'LIST': list_html(events, rv, now.date(), live),
        'REEL': reel_html(sched, events),
        'LIVE_LAYOUT': esc(live.get('layout', 'tate')),
        'CAL_DATA': json.dumps(events, ensure_ascii=False).replace('</', '<\\/'),
        'RV_OPTIONS': ''.join('<option value="%s">%d/%d(%s) %s</option>' % (esc(e['id']), e['m'], e['d'], esc(e['dow']), esc(e['title'])) for e in events),
        'RV_DM': esc(live.get('reserve_dm', '')),
        'VIDEO': video_html(S.get('video', {}), links),
        'NEWS': news_html(load_news(), now.date()),
        'PHOTOS': photo_html,
        'ICHIRAN': ichiran_html(sched),
        'GOODS': goods,
        'SHOP_TEXT': esc(S.get('shop', {}).get('text', '')),
        'SHOP_BTN': ('<a class="big-btn" href="%s" target="_blank" rel="noopener">%sを見る</a>'
                     % (esc(S['shop']['url']), esc(S['shop'].get('name') or 'ショップ'))) if S.get('shop', {}).get('url') else '',
        'MEMBERS': members_html(S.get('members', [])),
        'CONTACT_TEXT': esc(contact.get('text', '')),
        'MAIL_BTN': ('<button type="button" class="big-btn" id="mail-btn" data-m="%s" data-s="%s">メールする</button>'
                     % (base64.b64encode(mail.encode()).decode(), esc('【%sのホームページから】' % S.get('name', '')))) if mail else '',
        'DM_IG': ('<a class="big-btn" href="https://ig.me/m/%s" target="_blank" rel="noopener">InstagramのDM</a>' % esc(links['instagram'])) if links.get('instagram') else '',
        'DM_X': ('<a class="big-btn" href="%s" target="_blank" rel="noopener">XのDM</a>' % esc(x_url(links['x']))) if links.get('x') else '',
        'LINKS': link_row(links),
        'UPDATED': now.strftime('%Y-%m-%d %H:%M'),
        'YEAR': str(now.year),
    }
    for k, v in rep.items():
        page = page.replace('{{%s}}' % k, v)
    if not rv:
        page = re.sub(r'<!--RV-->.*?<!--/RV-->', '', page, flags=re.S)
    if not rep['SHOP_BTN'] and not goods:
        page = re.sub(r'<!--SHOP-->.*?<!--/SHOP-->', '', page, flags=re.S)
    with open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page.replace('{{PANEL}}', '').replace('{{FONT_URL}}', font_url([font if font in FONTS else 'noto', 'noto'])))
    if preview or mihon:   # 試し場：色と字を試すパネル付き。検索には出さない
        with open(os.path.join(ROOT, 'tools', 'panel.html'), encoding='utf-8') as f:
            panel = f.read().replace('{{FONTS}}', json.dumps({k: [v[0], v[2]] for k, v in FONTS.items()}, ensure_ascii=False))
        trial = (page.replace('{{PANEL}}', panel).replace('{{FONT_URL}}', font_url(FONTS))
                 .replace('<head>', '<head>\n<meta name="robots" content="noindex">', 1))
        if preview:
            with open(os.path.join(OUT, 'preview.html'), 'w', encoding='utf-8') as f:
                f.write(trial)
        if mihon:   # メンバーに配る見本：画像も中に入れた1ファイル（公開しない）
            d = os.path.join(ROOT, '_mihon')
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, '%sHP_見本.html' % S.get('name', 'band'))
            with open(path, 'w', encoding='utf-8') as f:
                f.write(inline_assets(trial))
            print('見本：%s（%d KB）' % (path, os.path.getsize(path) // 1024))
    open(os.path.join(OUT, '.nojekyll'), 'w').close()
    return len(events), len(photos)


if __name__ == '__main__':
    n, p = build('--preview' in sys.argv, sys.argv, '--mihon' in sys.argv)
    print('できました：ライブ予定 %d 件・写真 %d 枚 -> %s' % (n, p, OUT))
