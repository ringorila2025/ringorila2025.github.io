"""写真を photos/ に置く（Claudeのチャットから写真を足すとき用）

使い方：  py -3 tools/add_photo.py 写真のファイル [写真のファイル ...]

・長いほうの辺を 1600px までに縮め、jpg にして、位置情報などの情報を消して photos/ に置く
・名前は 日付_連番.jpg（例：2026-11-08_01.jpg）。同じ名前があるときは上書きせず、番号を進める
・置くだけです。公開（git push）は、たぬのOKをもらってから別にやります
"""
import datetime as dt
import os
import sys

from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'photos')
MAX = 1600


def main(paths):
    if not paths:
        sys.exit(__doc__)
    os.makedirs(OUT, exist_ok=True)
    today = dt.date.today().isoformat()
    for src in paths:
        try:
            im = Image.open(src)
            im = ImageOps.exif_transpose(im).convert('RGB')
        except Exception as e:
            print('読めませんでした（HEICはjpgにしてから）：', src, '-', e)
            continue
        im.thumbnail((MAX, MAX))
        n = 1
        while os.path.exists(os.path.join(OUT, f'{today}_{n:02d}.jpg')):
            n += 1
        dst = os.path.join(OUT, f'{today}_{n:02d}.jpg')
        im.save(dst, 'JPEG', quality=82, optimize=True)  # EXIF（位置情報など）は付けずに保存
        print('置きました：', os.path.relpath(dst, ROOT), f'{os.path.getsize(dst) // 1024}KB')


if __name__ == '__main__':
    main(sys.argv[1:])
