# 検証と保守

[入口](../README.md) · [出典](PROVENANCE.md)

印刷するだけなら、このページのPythonやFreeCADコマンドは不要です。
[印刷手順](PRINTING.md)を使ってください。ここは梱包・整合性を確認する人向けです。

## 確認できる範囲

| 確認 | 記録・方法 |
|---|---|
| 150個、21形状、23 BOM行、14枚3MF、28工程 | [kit.json](../verification/kit.json)／`scripts/verify_kit.py` |
| STLの閉鎖、辺の向き、頂点manifold、単一連結、正体積 | 同上。B21＋fit12＋試作用の追加1＝34 STL master |
| 3MFの実ジオメトリ・数量・色・配置・Z=0 | XMLを再読込し、対応STL・BOM・manifestと照合 |
| 個人Bのnative再open | [native.json](../verification/native.json)。150配置、正確な2行、外形・銘板寸法、銘板干渉候補 |
| 元担当の取付け確認 | [引継ぎnative記録](../verification/inherited-plate-native.json)。元のキャリアとの対称差0 |
| 手順・画像・PDF・ZIP | 相対リンク、個人PDF、SHA-256、ZIPの欠落・重複、機器情報／ローカルパスの混入を点検 |

3MF配置の256×256 mmと6 mmブリム余地の確認は**公称ベッドのデジタル検査**です。
実機の除外領域、校正線、ヘッド干渉、実ツールパスの保証ではありません。
実物試験・スライスは実施していません。`NOT_SLICED` を維持してください。

## ファイルを照合する

展開したルートの `SHA256SUMS.txt` は、配布内容のハッシュ一覧です。
WindowsではPowerShellの `Get-FileHash`、macOS/Linuxでは `shasum -a 256` 等で
個別ファイルを確認できます。例：

```powershell
Get-FileHash .\kit\B\parts\NP3-TEXT-B.stl -Algorithm SHA256
```

```bash
shasum -a 256 kit/B/parts/NP3-TEXT-B.stl
```

期待する銘板SHA-256：
`83ff7a42af4062b0e4a405edd64a8828ab218843d111d13961843fc0fe7044af`

ZIP自身のハッシュは、GitHub上の
[downloads/SHA256SUMS.txt](https://github.com/ktanino10/copilot-brick-gift-b/blob/main/downloads/SHA256SUMS.txt)
にあります。ZIPの中へ同じZIPを入れた二重配布はしていません。
ZIPを展開した後のダウンロードリンクだけは認証付きGitHubの入口であり、
組立・試作・図面・sourceのリンクは展開フォルダ内で完結します。

## 梱包と検査をやり直す

検証用Pythonライブラリは [requirements-verify.txt](../requirements-verify.txt)。
`pdftotext`（Poppler）も使います。FreeCADのnative検査は、別途FreeCAD 1.1.3の
対応Pythonとライブラリを使用しました。アプリ本体は同梱しません。

必要なライブラリがない場合だけ、専用仮想環境へ導入します。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-verify.txt
```

梱包を更新する順序：

```bash
.venv/bin/python scripts/build_print_kit.py
.venv/bin/python scripts/verify_kit.py --write-report
.venv/bin/python scripts/build_print_kit.py
.venv/bin/python scripts/verify_kit.py
```

最初の梱包を検査して報告を書き、その報告を含めて梱包・ハッシュを確定し、
最後は書き換えず再検査します。ZIPは固定のmember順・時刻で作ります。
各ZIP memberは相対パスで、B以外の模型、重複するmaster、nested ZIPを含みません。
生成ファイルは `docs/FILES.md`、`docs/STEPS.md`、`kit/B/steps.csv`、
`kit/manifest.json`、ハッシュ一覧、全キットZIPです。

### nativeを再openする

`FREECAD_PYTHON` をFreeCADに対応する埋込Python、
`FREECAD_LIB` を同じインストールのモジュールディレクトリへ設定してから実行します。
個人端末の絶対パスをこのリポジトリへ書き込まないでください。

```bash
mkdir -p .work
FREECAD_USER_HOME="$PWD/.work/freecad-profile" \
QT_QPA_PLATFORM=offscreen OMP_NUM_THREADS=2 \
PYTHONPATH="${FREECAD_LIB:?Set the matching FreeCAD library directory}" \
"${FREECAD_PYTHON:?Set the matching FreeCAD Python executable}" scripts/verify_native.py
```

これは専用プロセスでファイルを読んで閉じる検査です。
ユーザーが開いているGUI documentや他のworktreeを操作しません。
`FreeCAD` を先にimportしてから `Part` をimportします。
nativeをsave／saveAsせず、検査前後のhash一致も確認します。
寸法はtrimmed面の過大なBoundBoxを避けて `optimalBoundingBox` を使います。

`--refresh-catalog-metadata` は、既存nativeから銘板と全体の計算済みメタデータを
更新する保守オプションです。形状は生成しません。通常の再検査には不要です。
使用後は上記の梱包・検査をやり直してください。

### 元の配置計算だけを確認する

```bash
python3 source/scripts/design.py --output .work/new-layout-check
```

新しい未使用フォルダが必要です。Bと確定した2行以外は受け付けず、
配布source内のファイルへ上書きしません。
共通のgeometry builderと寸法sourceは保管していますが、このコマンドだけで
全CAD・PDF・3MFを再生成したことにはなりません。
機構や寸法を変える場合は、今回の「同形状再利用」の検証範囲外です。
旧STLと混ぜず、変更範囲を定めて別途再検証・試作してください。

## 非公開のまま保存する

uploadの直前に必ず以下を実行します。remoteのfetch／push先がこの独立private repoだけ、
`private=true`、`visibility=private`、`has_pages=false`、`fork=false` でないと停止します。

```bash
python3 scripts/check_private_target.py
```

公開元へのpush、visibility変更、Pages有効化、公開Releaseへのアップロードをしません。
自動upload workflowも含めていません。通常のnonforce pushの直前にも、この確認を行います。

native・図面の保存先を変更しても、機器のtoken・ID、Bambuの実設定入りプロジェクト、
人物写真・会話履歴をそのまま追跡対象へ追加しないでください。
実機の診断に必要なデータは内容と共有先を別途確認します。
