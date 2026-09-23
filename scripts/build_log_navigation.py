"""Private documentation navigation; leave the verified renderer and embedded geometry unchanged."""

import hashlib
from pathlib import Path

ANCHOR = '  <section class="start-card" aria-label="最初に読むこと">'
NAVIGATION = '''  <!-- PRIVATE_BUILD_LOG_NAV -->
  <aside id="build-record-nav" class="start-card" aria-label="実写真の制作記録">
    <strong><a href="../docs/BUILD-LOG.html">実写真の制作記録を読む</a></strong>
    <p>文字の問題から、銘板の試作報告、台座・前面の組立まで。写真で見える状態と、未確認の保持・寸法・完成模型の検証を分けています。</p>
    <p class="small">写真の記録はZIP全体を展開するとオフラインで読めます。3Dの動きは説明用CGで、写真や実組立動画ではありません。</p>
  </aside>
  <!-- /PRIVATE_BUILD_LOG_NAV -->
'''


def base_document(document):
    count = document.count(NAVIGATION)
    if count > 1:
        raise ValueError("The build-record navigation is duplicated.")
    if count == 1:
        base = document.replace(NAVIGATION, "", 1)
    else:
        base = document
    if "PRIVATE_BUILD_LOG_NAV" in base or 'id="build-record-nav"' in base:
        raise ValueError("The documentation-only navigation was changed unexpectedly.")
    return base


def add_navigation(document):
    base = base_document(document)
    if base.count(ANCHOR) != 1:
        raise ValueError("Cannot locate the single guide introduction.")
    return base.replace(ANCHOR, NAVIGATION + ANCHOR, 1)


def canonical_guide_hash(path):
    return hashlib.sha256(base_document(Path(path).read_text(encoding="utf-8")).encode()).hexdigest()
