# 個人B銘板・可読性改訂の承認記録

**この実CAD比較は2026-09-22に承認され、現行銘板へ採用されました。**
このフォルダは比較時の候補形状・測定・根拠の記録です。通常の印刷は
[現行の新版説明](../../docs/NAMEPLATE-V2.md)から行ってください。
候補ファイルと現行ファイルを別々の部品として二重に印刷しません。

![上は旧版、下が承認形状。同じ142mm幅、実native輪郭](preview/comparison-front.png)

2行の正確な文面、黒い基材142×40×2.4 mmと裏取付けは維持。
上段12 mm・下段10 mm、白い浮彫1.2 mm、全厚3.6 mmです。
前面の追加0.4 mmを含む完成模型の奥行は80.2 mmになります。

`candidate/plate.stl`／`.3mf`は同じ承認候補1個、`.FCStd`／`.step`は実nativeです。
`coupon/coupon.stl`／`.3mf`は同寸法glyphの小試験片で、縮小した全文ではありません。
どちらもSTLか3MFの一方を選びます。黒2.4 mm後のPauseは本人が実スライスで設定し、
3MFにprofile・Pause・G-codeが入っているとは扱いません。

[孔の拡大図](preview/counter-detail.png)・[実native断面](preview/side-section.png)・
[試験片](preview/coupon-front.png)・[全glyphの測定定義と値](metrics.json)・
[黒基材と連続解除経路の検査](motion-verification.json)を保存しています。
閉孔の中央帯chord、e/cの外へ抜ける有効開口、正線の代表gaugeと持続neckの判定を分けています。
0.2 mmノズルでも、ここで得た約1 mmを成功保証の規格とはしていません。

元写真やEXIFは含めていません。写真の糸引き・上面荒れ等は実設定が未受領のため
原因や補正値を断定せず、新版の実機結果も未確認です。

## 再現の範囲

同じリポジトリの`source/scripts/legible_lettering.py`と`legible_metrics.py`を利用します。
元のBlack、追加した正規Barlow Condensed Bold、OFLは改変していないフォント資源です。
Boldの出典は`google/fonts` commit `e44c4b011a820c2cbe2fd2cfa8052037d7edb571`。
`letter-plan.json`はこの個人2行専用で、別の文字列へ流用しません。
現行と旧版を取り違えないよう、比較の旧形状はrevision付き保管先を明示参照します。
通常ユーザーが再生成する必要はありません。
