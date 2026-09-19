# 出典と個人Bへの対応

[入口](../README.md) · [検証・保守](MAINTENANCE.md) · [権利表記](../notices/README.md)

## 採用範囲

このリポジトリは **B DESK CLASSICの個人向けキット**です。
既存Bの形状・取付け・配置を変更せず、通常の銘板1個を確定済みの個人銘板へ置き換えています。
追加キャラクター、別サイズ案、旧試験の4 mmピンは配布対象ではありません。
原本のGit履歴・バックアップ全体は取り込まず、明示された現行ファイルとBの保存済み媒体だけを
ハッシュ照合して選別しました。公開元のリポジトリ・worktreeを変更していません。

| 系統 | 固定した出典 |
|---|---|
| 共通の現行source | `ktanino10/copilot-brick-display`、commit `1eaae1288816ec9575eeb6e2abbe74ed53289d74` |
| 元の別PC・段階試作手順 | 同repo、生成／手順更新commit `7af459e5c5c9f0e3956bf785e34db20135a7ba97`。上記最新commitは検証記録の追記 |
| 共通形状revision | `4.0-public-template`。B非文字20形状、150配置、取付け仕様を再利用 |
| 個人銘板 | 元担当が検証したB用 `plate.stl`／`plate.3mf`／native。正確な2行、142×40×3.2 mm |
| 個人B完成native・PDF・画像 | 元担当が指定した保存済みBだけを選別。21 masterすべてが今回の採用STLとbyte一致 |
| 今回のキットrevision | `4.0-B-personal-kit.1`。梱包・B専用文書・個人版メタデータの統合であり、機構の再設計ではない |

各採用ファイルの出典相対パス、取得時のbytesとSHA-256は
[source-import.json](../verification/source-import.json)にあります。
`adapted:` はBだけの選別やパス・メタデータ整備を行ったものです。
同記録は取得時点の記録で、後のメタデータ更新を含む**納品時の全ハッシュは
[SHA256SUMS.txt](../SHA256SUMS.txt)** を正とします。

## 形状の置換は1枚だけ

| 採用ファイル | SHA-256 |
|---|---|
| `kit/B/parts/NP3-TEXT-B.stl` | `83ff7a42af4062b0e4a405edd64a8828ab218843d111d13961843fc0fe7044af` |
| `kit/B/plates/B-black-to-white-z2p4-01.3mf` | `45d3d3a47243b9d994aeab5b6c3744cbf7e6805912e0441db23acbb38fa2629c` |
| `source/native/NP3-TEXT-B.FCStd` | `72e2284f25cd3190ef9993cf12e5751e88d27718e8b0d2628bcbc547a1ab3b22` |
| `source/native/B.FCStd` | `c76b0dbbc6b3280b2efd2d2d97ca5e63a89a50864e897650e4d4914b23982755` |

通常版の文字入りSTLと対応3MFは、この印刷対象には含めていません。
個人板と同じ右ロゴを各1個、残り148個と合わせて**150個**です。
同じ銘板のSTL／3MFは代替形式であり、2個作る意味ではありません。
右ロゴと本体の単色3MFは元ファイルを無変更で使用しています。

元担当から引き継いだデジタル確認：

- [銘板nativeの確認](../verification/inherited-plate-native.json)：
  現行Bキャリアとの対称差0、完成配置の候補9ペアの最大干渉0、
  最小の実直線ストローク約1.4747 mm。
- [銘板梱包の確認](../verification/inherited-plate-package.json)：
  closed・vertex-manifold・正体積、3MFを再読込して1個、NOT_SLICED。
  ここでいう過去の小ZIPは出典記録だけで、今回の配布経路ではありません。

今回の専用worktreeでも、[nativeを再openした結果](../verification/native.json)で
150個のID・色・配置、完成外形、2行、銘板寸法、個人plateとの対称差0、
候補9ペアの最大干渉0を確認しています。nativeは書き換えていません。
元の公開キャリアとの比較結果は、元担当の記録として区別して保持します。

## 画像・図面を混同しない

`docs/images/B-hero.png` と `B-base-front.png` は、個人2行が入った
保存済みの実STL由来Blenderレンダーです。今回新しい顔・動画を作っていません。
`nameplate-front.png` は直近の個人銘板の実CAD正面投影で、白背景の輪郭図です。
`nameplate-print-orientation.svg` だけは、姿勢と色替え高さを説明する模式図です。
いずれも実物写真・実スライス成功例ではありません。

個人BのPDFとB工程SVGには、保存時のヘッダー **`REV3`** が残っています。
その保存済みBの非文字20 masterは現行共通形状とbyte一致、文字masterも直近個人板とbyte一致、
配置JSONとBOMも現行と一致するため、同じ形状・配置の図として採用しました。
印刷時は「REV3」というヘッダーだけを理由に別の旧ZIPを探さず、このキット内の対応表を使います。

`kit/fit/interface.*`、`front-interface.svg`、非文字部品の寸法SVGは**共通形状の参考図**です。
`PUBLIC TEMPLATE` という元ヘッダーは来歴の表示で、個人完成図や公開配布の指示ではありません。
個人文字が見える銘板図・完成画像・PDFは、すべて今回の確定2行に対応しています。

## 元generatorと寸法source

`source/design/parameters.json` は機械寸法・Bの離散配置と個人2行、
`catalog.json` はB＋必要fit／trialだけの形状定義、`interface.json` は接続仕様です。
個人銘板のhash・三角形数・CAD体積・重心と完成Bの集計値は、今回の再open結果へ更新し、
通常版の文字の集計値を残していません。

`source/scripts/` に、元の機械geometry・前面機構・文字幅測定・配置generatorを保持しています。
`freecad_geometry.py`、`front_nameplate.py`、`letter_metrics.py` はそのままです。
`design.py` はBと確定2行のみ許可し、公開用ポリシーや公開サイト出力に依存せず、
新しいローカル出力先だけを使うよう入口を適応しました。配置・寸法の計算は変えていません。

Barlow Condensed BlackとOFL、元マークの派生輪郭を保持しました。
元写真・人物画像、不要なBlenderファイル／動画／フレーム、公開用workflow・CNAME・Pages設定、
会話履歴、端末の絶対パス、プリンタID・tokenは含めません。
元プロジェクト全体のビルドやサイト公開手順は、このキットの利用に必要ありません。

## 検証の限界

closed／manifold、CAD干渉0、正しい配置、ハッシュ一致は**印刷成功の保証ではありません**。
現物の嵌合、keeper保持、台座の反り、強度、転倒、P1SでのPause・手動交換・再開は未試験です。
実装ノズル、PLA銘柄／色、plate、処理profile、AMS有無、実設定入りBambuプロジェクトは
まだ確認できていません。本人の実スライスと段階試作を省略しないでください。
