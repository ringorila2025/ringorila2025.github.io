# リンゴリラのホームページ（Claudeへ）

公開先：https://ringorila2025.github.io/ （GitHub：ringorila2025/ringorila2025.github.io、mainにpushすると数分で公開）
たぬ（松たぬら）が、Claudeのチャットから「ニュースを出して」「写真を足して」「ライブ情報を直して」と頼むための手順書です。

## 守ること

- **push（公開）は、たぬのOKをもらってから。** 先に「何を足すか」を見せて、「出していい？」と聞く
- 返事は日本語で
- 音源・動画のファイルは置かない（YouTubeなどの埋め込みで）
- メールなどの個人情報は、ページにもファイルにも書かない（メールは GitHub の鍵 `CONTACT_MAIL`）
- ファイルの削除・上書きは、事前にたぬに確認
- 推測と確定は分けて書く
- 見た目（色・字・並び）を変えるときは、たぬが選ぶ（お任せにしない）

## お知らせ（news.md）

```bash
py -3 tools/add_news.py "新しい動画をあげました！ https://youtu.be/xxxxxxxxxxx"
py -3 tools/add_news.py "グッズができました" --date 2026-11-20
```

- 1行 = 1お知らせ。日付が新しい順に5つ出る。URLはボタンに、YouTubeのURLは新しい3つまで動画になる
- 消すときは news.md のその行を消す（たぬに確認してから）

## 写真（photos/）

```bash
py -3 tools/add_photo.py 写真のファイル.jpg
```

- 1600pxに縮めて、位置情報を消して、`日付_連番.jpg` で photos/ に置く（上書きしない）
- チャットに貼られた写真が**ファイルとして取り出せるか**は、環境による。取り出せないときは、たぬに「PCに保存した写真のパス」か「pCloud／Googleドライブの場所」を聞く
- HEICは読めない。jpg/png/webp にしてから

## ライブ情報

ページはGoogleカレンダー（リンゴリラのイベントカレンダー）から**自動**で1日3回作る。直すのはカレンダーの方。
- まだ言えない予定は、タイトルか説明欄に `#解禁前`
- すぐ反映したいとき：`gh workflow run site.yml -R ringorila2025/ringorila2025.github.io --ref main`
- 鍵 `CAL_ICS_URL` はいま、カレンダーの**公開用アドレス**。カレンダーを非公開にしたら、非公開アドレスに入れかえる（`gh secret set CAL_ICS_URL -R ringorila2025/ringorila2025.github.io`。値はたぬが貼る）

## 手元で確かめる → 公開する

```bash
py -3 tools/build.py --preview      # _site/ に作る（見本のパネル付き）。公開はされない
```

たぬのOKが出たら、自分が変えたファイルだけを commit して push する。

```bash
git add news.md photos
git commit -m "🍏 お知らせ／写真を足した"
git push
```

push のあと `gh run list -R ringorila2025/ringorila2025.github.io --limit 1` で、公開の作業が成功したか見る。

## そのほか

- 設定は `settings.toml`、使い方の全部は `README.md`
- Windowsでは `python` ではなく `py -3`
- ファイルの改行は元のまま保つ（news.md / README は LF、build.py / template.html は CRLF）
