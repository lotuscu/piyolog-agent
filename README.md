# PiyoLog briefing

English | [日本語](#日本語)

Unofficial local tools that let a parent point an AI agent at their own [PiyoLog](https://www.piyolog.com/app/piyolog/data_feed/en/index.html) data feed and get a repeatable daily summary of feeding, sleep, and diapers.

**Not affiliated with, endorsed by, or maintained by the makers of PiyoLog.** This repository only fetches the feed the parent creates and summarizes it on their own machine.

The feed URL is a password. Do not commit it, post it, or screenshot it.

## For AI agents

Read [AGENTS.md](AGENTS.md) and follow it. It contains a complete, self-contained setup for **Muse** (install the skill, store the secret, schedule twice-daily briefings) and shorter notes for other agents. A ready-made skill file is at [skills/piyolog/SKILL.md](skills/piyolog/SKILL.md).

## Quick start (humans)

Python 3.9 or newer. Nothing to install.

1. In the PiyoLog app: Settings → Data Feed → Create New Feed. Pick the child, a time range, and an expiration, then copy the URL. There is no separate API key; the URL is the credential.
2. Save the URL locally, never in git:

```bash
git clone https://github.com/lotuscu/piyolog-briefing.git
cd piyolog-briefing
printf '%s\n' 'PASTE-YOUR-FEED-URL-HERE' > .feed_url
```

(Or export `PIYOLOG_FEED_URL`. `.feed_url` and `.env` are gitignored; see `.env.example`.)

3. Fetch and summarize:

```bash
python3 fetch.py
python3 summarize.py --days 1
```

`fetch.py` writes a timestamped snapshot plus a deduplicated store under `data/` (`records.jsonl` is canonical; CSV and SQLite views are generated from it). Run it about twice a day: a free feed only returns the last ~24 hours, so a longer gap loses records for good. The store keeps what you already fetched, keyed by `event_id`.

## What the summary reports

Per local day (timezone `PIYOLOG_TZ`, default `Asia/Tokyo`; feed timestamps are UTC):

- Milk ml by type (formula, expressed breast milk, breastfeeding amount, pumping — pumping is **not** counted as a bottle the baby drank)
- Breastfeeding minutes (left + right). Minutes are never converted to ml.
- Sleep total and longest stretch. `Sleep` and `WakeUp` are separate records; the tool pairs each `Sleep` with the next `WakeUp` and splits stretches at midnight.
- Pee and poop counts and longest gaps; solid foods from the memo with the first date each food appears; max temperature; counts of vomiting, rash, cough, medicine, hospital, injury when logged.

Markdown rounds minutes to whole numbers; JSON keeps exact values. A record deleted in the app disappears from later feeds but stays in the local store.

## Feed facts (from the official guide, checked October 2026)

- [English guide](https://www.piyolog.com/app/piyolog/data_feed/en/index.html) · [Japanese guide](https://www.piyolog.com/app/piyolog/data_feed/ja/index.html)
- Free account: one feed, ~24-hour range, expires 90 days after creation. Premium: up to five feeds, longer ranges and expirations.
- Settings cannot be edited. Revoke and recreate to change anything.
- HTTP 404 `feed_unavailable` means expired, revoked, paused, wrong URL, or deleted child. A brand-new feed can also 404 for about a minute. `fetch.py` treats 401 the same.
- Do not poll faster than about once a minute. Twice a day is enough.

## Optional Postgres

Local files are the default and the only thing `summarize.py` reads. If you also want a copy in your own Postgres (for example Neon), see [docs/postgres.md](docs/postgres.md). Never commit a connection string.

## Commands

```bash
python3 fetch.py                                    # fetch + update local store
python3 fetch.py --backend postgres               # also upsert into DATABASE_URL
python3 neon_https_sync.py                          # or sync to Neon over HTTPS (works on Muse)
python3 summarize.py --days 2 --format both         # Markdown + JSON
python3 summarize.py --from 2026-09-08 --to 2026-09-09 --format json
python3 -m unittest discover -s tests -t . -v       # tests (synthetic fixture only)
```

## License

[MIT](LICENSE)

---

## 日本語

ぴよログ（PiyoLog）のデータフィードを保護者本人の AI エージェントが読み取り、授乳・睡眠・おむつの日次サマリーを作るための、非公式のローカルツールです。

**PiyoLog 公式とは関係ありません。** このリポジトリは、保護者が自分で作成したフィードを取得し、自分のマシン上で要約するだけです。

フィード URL はパスワードです。コミットしたり、公開したり、スクリーンショットに残したりしないでください。

### AI エージェント向け

[AGENTS.md](AGENTS.md) を読んで、その手順に従ってください。**Muse** 向けの完全なセットアップ（スキルのインストール、秘密情報の扱い、1日2回の定時実行）が含まれています。スキルファイルは [skills/piyolog/SKILL.md](skills/piyolog/SKILL.md) にあります。

### クイックスタート（人間向け）

Python 3.9 以上が必要です。インストールするものはありません。

1. ぴよログアプリで「設定 → データフィード → 新規作成」。子ども・期間・有効期限を選んで URL をコピーします。API キーは別途なく、URL 自体が認証情報です。
2. URL は git に入れず、ローカルに保存します。

```bash
git clone https://github.com/lotuscu/piyolog-briefing.git
cd piyolog-briefing
printf '%s\n' 'ここにフィードURL' > .feed_url
```

（`PIYOLOG_FEED_URL` 環境変数でも可。`.feed_url` と `.env` は gitignore 済みです。）

3. 取得と要約：

```bash
python3 fetch.py
python3 summarize.py --days 1
```

`fetch.py` はスナップショットと重複排除済みストアを `data/` に書きます。無料フィードは直近約24時間分しか返さないため、1日2回程度の実行が目安です。間隔が空くと、取りこぼした記録は二度と戻りません。

### サマリーの内容

現地の1日ごと（タイムゾーンは `PIYOLOG_TZ`、既定は `Asia/Tokyo`。フィードの時刻は UTC）に、種類別ミルク量（ml）、授乳時間（分。ml には換算しません）、睡眠の合計と最長区間（`Sleep` と `WakeUp` をペアにします）、おしっこ・うんちの回数と最長間隔、離乳食（メモから抽出、初出日つき）、最高体温、その他の記録回数を出します。搾乳は「飲んだミルク」には数えません。

### フィードの仕様（公式ガイドより、2026年10月確認）

- [日本語ガイド](https://www.piyolog.com/app/piyolog/data_feed/ja/index.html) · [英語ガイド](https://www.piyolog.com/app/piyolog/data_feed/en/index.html)
- 無料アカウント：フィード1つ、範囲は約24時間、作成から90日で失効。プレミアムは最大5つ、範囲・期限を拡張できます。
- 設定は後から変更できません。変更するには取り消して作り直します。
- HTTP 404 `feed_unavailable` は、失効・取り消し・停止・URL 間違い・子どもの削除のいずれかです。作成直後は1分ほど404になることもあります。
- 同じ URL へのアクセスは1分に1回程度まで。1日2回で十分です。

### Postgres（任意）

既定はローカルファイルのみで、`summarize.py` が読むのもローカルです。Neon などの自分の Postgres にもコピーしたい場合は [docs/postgres.md](docs/postgres.md) を見てください。接続文字列は絶対にコミットしないでください。

### ライセンス

[MIT](LICENSE)
