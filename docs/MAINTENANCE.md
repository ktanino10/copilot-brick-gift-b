# 検証と保守

[入口](../README.md) · [出典](PROVENANCE.md)

印刷するだけ、または3Dガイドを見るだけなら、このページのPython・Node・FreeCADコマンドは不要です。
ZIPを展開して`guide/index.html`をダブルクリックし、[印刷手順](PRINTING.md)を使ってください。
ここは梱包・整合性を確認する人向けです。

## 確認できる範囲

| 確認 | 記録・方法 |
|---|---|
| 150個、21形状、23 BOM行、14枚3MF、28工程 | [kit.json](../verification/kit.json)／`scripts/verify_kit.py` |
| STLの閉鎖、辺の向き、頂点manifold、単一連結、正体積 | 同上。B21＋fit12＋接続試作1＝34 masterに、別の文字試験片1を追加 |
| 3MFの実ジオメトリ・数量・色・配置・Z=0 | XMLを再読込し、対応STL・BOM・manifestと照合 |
| 個人Bのnative再open | [native.json](../verification/native.json)。150配置、正確な2行、外形・銘板寸法、銘板干渉候補 |
| 元担当の取付け確認 | [引継ぎnative記録](../verification/inherited-plate-native.json)。元のキャリアとの対称差0 |
| 手順・画像・PDF・ZIP | 相対リンク、個人PDF、SHA-256、ZIPの欠落・重複、機器情報／ローカルパスの混入を点検 |
| 全150slotと全150配置の双方向対応 | `scripts/verify_guide_mapping.py`。全14実3MFの順番・位置、全候補、便宜割当、23 part/color群、工程、寸法、STLのbyte一致 |
| オフライン3Dの実ブラウザ操作 | [guide-browser.json](../verification/guide-browser.json)。通信遮断したChromiumで150組の双方向対応、14枚と23部品ID／色群の実選択、28工程、再生停止、90度姿勢、320〜1440 px、keyboard、カメラの枠内表示 |
| ガイドの通信不要・配布資源 | `scripts/verify_offline_html.py`。classic runtime／CSS／meshを埋込、外部active resourceなし、CSP `connect-src 'none'` |

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

期待する新版銘板SHA-256は[現行一覧](../SHA256SUMS.txt)の
`kit/B/parts/NP3-TEXT-B.stl`と照合します。旧版のhashを新版の合格値にしません。

今回の可読性改訂は[変更説明と測定値](NAMEPLATE-V2.md)を参照してください。
`requirements-cad.txt`は図面をまとめ直すReportLab／svglib／pypdfと、輪郭測定のShapely／SciPyを追加します。
変更したのは銘板1形状だけで、元の20形状／13プレート／150配置の不変を別途検査します。

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
.venv/bin/python scripts/build_b_guide.py
.venv/bin/python scripts/verify_guide_mapping.py
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
npm run test:guide-model
.venv/bin/python scripts/verify_guide_browser.py --capture --write-report
.venv/bin/python scripts/build_print_kit.py
.venv/bin/python scripts/verify_kit.py --write-report
.venv/bin/python scripts/build_print_kit.py
.venv/bin/python scripts/verify_kit.py
.venv/bin/python scripts/verify_extracted_guide.py
```

最初の梱包を検査して報告を書き、その報告を含めて梱包・ハッシュを確定し、
最後は書き換えず再検査します。ZIPは固定のmember順・時刻で作ります。
各ZIP memberは相対パスで、B以外の模型、重複するmaster、nested ZIPを含みません。
文字試験片は`samples/nameplate-v2/`に別区分で入れ、150個の組立プレートへ加えません。
revision付きの旧銘板や未選択の候補フォルダは現行印刷ZIPの収録対象外です。
生成ファイルは `guide/index.html`／`index.mapping.json`、実ビューアのPNG／GIF、
`docs/FILES.md`、`docs/STEPS.md`、`kit/B/steps.csv`／`part-map.csv`、
`kit/manifest.json`、検証記録、ハッシュ一覧、全キットZIPです。
manifestは印刷データのinventoryに加え、HTMLとmappingのbytes／SHAも持ちます。
HTMLを変更した後で古いbrowser検証を流用すると、entry hashが一致せず梱包検査が停止します。
最後の`verify_extracted_guide.py`は、生成ZIPを一時フォルダへ展開してブラウザで開き、
さらにHTMLだけを日本語・空白を含む別名へコピーして再確認します。
ネット遮断下で最初の1個と全150個を表示し、一時フォルダは終了時に削除します。

### ガイド生成・撮影の依存を用意する場合

必要なパッケージがない場合だけ、[requirements-guide.txt](../requirements-guide.txt)を使用します。
既存の検証用依存にPlaywrightとPillowを加えたもので、閲覧用PCへの導入は不要です。

```bash
.venv/bin/python -m pip install -r requirements-guide.txt
.venv/bin/python -m playwright install chromium
```

ブラウザ検査は独立したheadless Chromiumを使い、ユーザーの開いているブラウザを操作しません。
通信をofflineにし、HTTP／HTTPS／WebSocketを記録・遮断して要求0を確認します。
`--capture`で出力する画像・GIFは同じビューアの実renderです。中間フレームは配布しません。
`--entry`には展開ZIP内の別の`guide/index.html`も指定できるため、梱包後の実ファイルを検査できます。
成功時のみ`--write-report`で記録し、通常の検査はファイルを変更しません。

同梱ランタイムは`web/assembly-guide/runtime.js`です。コードを変更せず、入力を反映し直すだけなら
`build_b_guide.py`がこれを使うため、Nodeでのbundle作成は不要です。
共通viewerコードを更新する場合だけ、[package.json](../package.json)とlockのexact依存で再bundleします。
Three.js 0.180.0はMIT、esbuild 0.25.10はbuild用です。

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run build:guide-runtime
```

その後に上記のガイド生成・browser撮影・梱包検査を一巡します。
共有sourceの取り込みは明示されたファイルだけを読み、自分のworktreeでbuildします。
公開側へ個人データを渡したり、他worktreeでbuildしてはいけません。

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
