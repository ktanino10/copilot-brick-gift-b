# 出典と個人Bへの対応

[入口](../README.md) · [検証・保守](MAINTENANCE.md) · [権利表記](../notices/README.md)

## 採用範囲

このリポジトリは **B DESK CLASSICの個人向けキット**です。
非文字20形状・黒い取付け基材・150配置を維持し、文字銘板1個だけを
2026-09-22承認の可読性改訂版へ更新しています。
追加キャラクター、別サイズ案、旧試験の4 mmピンは配布対象ではありません。
原本のGit履歴・バックアップ全体は取り込まず、明示された現行ファイルとBの保存済み媒体だけを
ハッシュ照合して選別しました。公開元のリポジトリ・worktreeを変更していません。

| 系統 | 固定した出典 |
|---|---|
| 共通の現行source | `ktanino10/copilot-brick-display`、commit `1eaae1288816ec9575eeb6e2abbe74ed53289d74` |
| 元の別PC・段階試作手順 | 同repo、生成／手順更新commit `7af459e5c5c9f0e3956bf785e34db20135a7ba97`。上記最新commitは検証記録の追記 |
| 共通形状revision | `4.0-public-template`。B非文字20形状、150配置、取付け仕様を再利用 |
| 個人銘板 | 現行は実ink高12／10 mm・白1.2 mmの承認形状。142×40×3.6 mm。正確な2行は不変 |
| 個人B完成native・PDF・画像 | 保存済みBの文字部品だけ差し替え、関係する投影・実STL画像を更新。他149組込solidは幾何一致 |
| 今回のキットrevision | `4.1-B-legibility.1`。文字面だけの改訂。白が0.4 mm前に出るため全体奥行は80.2 mm |

各採用ファイルの出典相対パス、取得時のbytesとSHA-256は
[source-import.json](../verification/source-import.json)にあります。
`adapted:` はBだけの選別やパス・メタデータ整備を行ったものです。
同記録は取得時点の記録で、後のメタデータ更新を含む**納品時の全ハッシュは
[SHA256SUMS.txt](../SHA256SUMS.txt)** を正とします。

## 現行と旧版を分ける

| 現行ファイル | 対応 |
|---|---|
| `kit/B/parts/NP3-TEXT-B.stl` | 新版の文字銘板1個 |
| `kit/B/plates/B-black-to-white-z2p4-01.3mf` | 同じ新版1個の代替形式。Pauseは未設定 |
| `source/native/NP3-TEXT-B.FCStd` | 新版の実native、実STEPも同じ形状 |
| `source/native/B.FCStd`／`B.step` | 同じ150配置へ新版だけを差し替えた完成native／STEP |

現行のSHA-256は[配布一覧](../SHA256SUMS.txt)を参照してください。
旧銘板（下段8 mm・白0.8 mm）は
[revision付きの保管先](https://github.com/ktanino10/copilot-brick-gift-b/tree/main/revisions/4.0-B-personal-kit.2)
に残しました。現行印刷ZIPには旧板を混ぜません。

通常版の文字入りSTLと対応3MFは、この印刷対象には含めていません。
個人板と同じ右ロゴを各1個、残り148個と合わせて**150個**です。
同じ銘板のSTL／3MFは代替形式であり、2個作る意味ではありません。
右ロゴと本体の単色3MFは元ファイルを無変更で使用しています。

旧版の元担当から引き継いだデジタル確認（新版の値と混同しません）：

- [銘板nativeの確認](../verification/inherited-plate-native.json)：
  現行Bキャリアとの対称差0、完成配置の候補9ペアの最大干渉0、
  最小の実直線ストローク約1.4747 mm。
- [銘板梱包の確認](../verification/inherited-plate-package.json)：
  closed・vertex-manifold・正体積、3MFを再読込して1個、NOT_SLICED。
  ここでいう過去の小ZIPは出典記録だけで、今回の配布経路ではありません。

今回の専用worktreeでも、[nativeを再openした結果](../verification/native.json)で
150個のID・色・配置、完成外形、2行、銘板寸法、個人plateとの対称差0、
候補9ペアの最大干渉0を確認しています。
今回は実際に文字nativeを更新し、完成native中の他149個は幾何的に同じまま保存しました。
曲線方向ベクトルの丸めにより旧BRep文字列とbyte差が出た右ロゴも、体積対称差0・面数・外形一致です。
印刷用の非文字20 STL／他13枚の3MFはbyte不変更です。
元の公開キャリアとの比較結果は、元担当の記録として区別して保持します。

## 画像・図面を混同しない

`docs/images/B-hero.png` と `B-base-front.png` は、個人2行が入った
現行の実STLを同じオフラインビューアで描画した画像です。
初回の旧Blender画像を、新版の完成画像と称していません。
`nameplate-front.png` は新版の実CAD正面投影です。
`nameplate-print-orientation.svg` だけは、姿勢と色替え高さを説明する模式図です。
いずれも実物写真・実スライス成功例ではありません。

非文字部品のSVGには保存時のヘッダー **`REV3`** が残っています。
変更していない共通部品の図として使用します。文字が見える全体図・分解図・銘板図、
前面の実断面、銘板を含む工程の平面範囲は新版に対応させ、PDFをまとめ直しています。
全体の前・右・上の図は、実STLの少し見下ろす正投影ビューです。
寸法ラベルはnativeの外接値で、画像の画素を測る図ではありません。
銘板の輪郭・断面と前面取付け断面は実native由来です。

`kit/fit/interface.*`、`front-interface.svg`、非文字部品の寸法SVGは**共通形状の参考図**です。
`PUBLIC TEMPLATE` という元ヘッダーは来歴の表示で、個人完成図や公開配布の指示ではありません。
個人文字が見える銘板図・完成画像・PDFは、すべて今回の確定2行に対応しています。

## オフライン3Dガイドと新しい案内画像

[`guide/index.html`](../guide/index.html)は、承認済みBの実STL・実3MF・assemblyを照合し、
描画ランタイムと圧縮STLを1つのHTMLへ埋め込んだものです。
`guide/index.mapping.json`はその対応表、`kit/B/part-map.csv`は全150slotの表です。
同形同色の全候補と便宜割当を分け、刻印や実物個体の識別とは扱いません。
取付け機構、色、150配置は再設計・再配置していません。
埋め込まれた銘板メッシュだけが今回の新版へ更新されています。

共通のviewer／mapping generatorだけを`ktanino10/copilot-brick-display`の担当者から
限定pathでread-only取得しました。共通案内コードの固定commitは
`35ebc11234779424ebbda83b3f1b7d31d8518b24`（UI v1.3）で、
形状の出典commit `1eaae1288816ec9575eeb6e2abbe74ed53289d74`とは別です。
取り込みのファイル別SHA-256と版は
[guide-source-import.json](../verification/guide-source-import.json)に記録しています。
個人source、銘板、画像、生成HTMLを公開側へ送り返していません。
当初はprivate／Pagesなしで保存しました。2026-09-23のユーザーによる追加承認後は
個人版repoをpublic化し、選別した案内をPagesでも公開します。保存したローカルHTMLも引き続き使えます。

`docs/images/B-guide-start.png`、`B-guide-front.png`、
`B-guide-base-front.gif`は、この同梱ビューアをオフラインの実ブラウザで描画・撮影したものです。
GIFは空の机から`B-001`〜`B-024`の24個を追加し、台座5段・前面2個・keeper3個までを示します。
銘板の90度回転、黒2.4 mm／白1.2 mmと、変更していないロゴ黒2.8 mm／白0.8 mmは実形状です。
軌跡や着地点の透過表示は説明用で、物理シミュレーションではありません。
[ブラウザ検証](../verification/guide-browser.json)は表示・操作の確認であり、実機の合格証拠ではありません。

## 元generatorと寸法source

`source/design/parameters.json` は機械寸法・Bの離散配置と個人2行、
`catalog.json` はB＋必要fit／trialだけの形状定義、`interface.json` は接続仕様です。
個人銘板のhash・三角形数・CAD体積・重心と完成Bの集計値は、今回の再open結果へ更新し、
通常版の文字の集計値を残していません。

`source/scripts/` に、元の機械geometry・前面機構・文字幅測定・配置generatorを保持しています。
`freecad_geometry.py`、`letter_metrics.py` の共通機械・既存正線測定はそのままです。
`front_nameplate.py` は承認済みの文字計画に対応し、`legible_lettering.py`と
`legible_metrics.py`が閉孔・e出口・追加字間の限定処理と定義済み測定を提供します。
`source/design/nameplate-plan.json`は正確な個人2行に対する計画で、公開側へ流用しません。
`design.py` はBと確定2行のみ許可し、公開用ポリシーや公開サイト出力に依存せず、
新しいローカル出力先だけを使うよう入口を適応しました。配置・寸法の計算は変えていません。

Barlow Condensed BlackとOFL、元マークの派生輪郭を保持し、正規のBoldを追加しました。
Boldの出典は`google/fonts` commit `e44c4b011a820c2cbe2fd2cfa8052037d7edb571`です。
公開側へ渡したのは個人値を持たない共通関数とBold/OFLだけです。
制作記録にはユーザーが掲載を許可した回転・切り取り・メタデータ除去済みの実写真9枚だけを追加しました。
加工前の原画像・元のファイル名・EXIF・元パス対応表は含めません。
以前の記録にあるprivate生成モードは当時の来歴で、現在の公開設定を示すものではありません。
[最新の公開方針](../publication/README.md)を参照してください。
不要なBlenderファイル／旧動画／中間フレーム、公開用workflow・CNAME・Pages設定、
会話履歴、端末の絶対パス、プリンタID・tokenも含めません。
元プロジェクト全体のビルドやサイト公開手順は、このキットの利用に必要ありません。

## 検証の限界

closed／manifold、CAD干渉0、正しい配置、ハッシュ一致は**印刷成功の保証ではありません**。
文字試作・台座・前面部品の実写真と本人報告は[制作記録](BUILD-LOG.md)にあります。
現物の正確な寸法、keeper保持力、強度、転倒、P1Sの交換手順等の正式な評価結果は未提供です。
9/22の0.2 mmノズル申告と9/23の手応え・土台組立報告は、使用した版のhash照合や模型全体の実証とは分けています。
PLA銘柄／色、plate、処理profile、AMS有無、実設定入りBambuプロジェクトは未照合です。
本人の実スライスと段階試作を省略しないでください。
