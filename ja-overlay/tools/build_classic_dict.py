#!/usr/bin/env python3
"""Merge seed dictionary, translated Classic UI chunks, and dynamic patterns into assets/ja_classic_dict.json."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo/
WORKSPACE = ROOT.parent
JA_OVERLAY = ROOT / "ja-overlay"
CLASSIC_DIR = WORKSPACE / "translations" / "classic"
CHUNKS_DIR = CLASSIC_DIR / "chunks"
OUT_DICT = JA_OVERLAY / "assets" / "ja_classic_dict.json"

# Never translate pure identifiers/units/versions even if an accidental pair exists
FORBIDDEN_EXACT_KEYS = {
    "", " ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "OK", "ID", "URL", "FPS", "GPU", "CPU", "RAM", "VRAM", "X11", "DLL", "API",
    "HUD", "HDR", "HDR10", "SDR", "USB", "DPI", "MB", "GB", "KB", "Hz", "ms",
    "x86", "x64", "ARM64", "WoW64", "DXVK", "VKD3D", "D7VK", "Wine", "Proton",
    "Box64", "FEXCore", "Turnip", "Zink", "VirGL", "Vulkan", "OpenGL", "Wayland",
    "yserver", "Steam", "Epic", "GOG", "Amazon", "Xbox", "Gamescope", "MangoHud",
    "WineD3D", "CNC DDraw", "Mesa", "Adreno", "Mali", "PanVK", "C:", "D:", "Z:",
    "1.0", "1.1", "1.2", "1.3", "1.4", "2.0", "2.1", "3.0", "3.1", "4.0",
    "Auto", "LSFG Native", "Win-FG Native", "LSFG-VK", "WFG",
}

# Dynamic UI patterns (Kotlin $interpolation rendered through Text(...))
DYNAMIC_PATTERNS = [
    # SettingsScreen / Updates
    {"regex": r"^Installed:\s*V\s*(.+?)\s+[•·]\s+Latest:\s*V\s*(.+)$", "replace": "インストール済み: V $1  •  最新: V $2"},
    {"regex": r"^Installed:\s*V\s*(.+)$", "replace": "インストール済み: V $1"},
    {"regex": r"^[·•]\s*Latest:\s*V\s*(.+)$", "replace": "• 最新: V $1"},
    {"regex": r"^Download & install V\s*(.+)$", "replace": "V $1 をダウンロードしてインストール"},
    {"regex": r"^V\s*([0-9][0-9A-Za-z._-]*)$", "replace": "V $1"},
    {"regex": r"^·\s*latest\s*V\s*(.+)$", "replace": "· 最新 V $1"},
    {"regex": r"^Bannerlator\s+(.+)\s+is\s+available$", "replace": "Bannerlator $1 が利用可能です"},
    {"regex": r"^Current:\s*(.+)$", "replace": "現在: $1"},
    {"regex": r"^Latest:\s*(.+)$", "replace": "最新: $1"},
    {"regex": r"^\(small update,\s*full app\s*(.+)\)$", "replace": "（差分アップデート・フルサイズ $1）"},
    {"regex": r"^Updating to V\s*(.+)$", "replace": "V $1 へアップデート中"},
    {"regex": r"^of\s+(.+)$", "replace": "/ $1"},
    {"regex": r"^about\s+(.+)\s+left$", "replace": "残り約 $1"},
    {"regex": r"^Update to V\s*(.+)\s+failed$", "replace": "V $1 へのアップデートに失敗しました"},
    {"regex": r"^Imported from Steam store \(Lossless Scaling\)\s*—\s*(.+)\s*MB$", "replace": "Steam ストア（Lossless Scaling）からインポート済み — $1 MB"},
    {"regex": r"^Imported manually\s*—\s*(.+)\s*MB$", "replace": "手動インポート済み — $1 MB"},
    {"regex": r"^Imported\s*\((.+)\s*MB\)$", "replace": "インポート済み（$1 MB）"},
    {"regex": r"^Shaders ready for LSFG Native\s*\(built in\s*(.+)s\)$", "replace": "LSFG Native 用シェーダーの準備完了（$1 秒）"},
    {"regex": r"^Backup completed:\s*(.+)$", "replace": "バックアップ完了: $1"},
    {"regex": r"^Diagnostic log saved:\s*(.+?)\s*—\s*share this file$", "replace": "診断ログを保存しました: $1 — このファイルを共有してください"},
    {"regex": r"^Saved to\s+(.+?)\s*—\s*share this file with us\.$", "replace": "$1 に保存しました — このファイルを共有してください。"},
    {"regex": r"^(\d+)\s+Bindings\s*·\s*🔋\s*(\d+)%$", "replace": "$1 件の割り当て · 🔋 $2%"},
    {"regex": r"^(\d+)\s+Bindings$", "replace": "$1 件の割り当て"},
    {"regex": r"^🎮\s*(\d+)\s+binds$", "replace": "🎮 $1 件の割り当て"},
    {"regex": r"^Key:\s*(.+)$", "replace": "キー: $1"},

    # ContainerDetailScreen & Settings
    {"regex": r"^Select folder for drive\s+([A-Z]):$", "replace": "ドライブ $1: のフォルダーを選択"},
    {"regex": r"^([A-Za-z0-9._-]+)\s+Version$", "replace": "$1 バージョン"},
    {"regex": r"^([A-Za-z0-9._-]+)\s+Preset$", "replace": "$1 プリセット"},
    {"regex": r"^([A-Za-z0-9._-]+)\s+Configuration$", "replace": "$1 設定"},
    {"regex": r"^What's new in\s+(.+)$", "replace": "$1 の新機能"},
    {"regex": r"^GPU name spoof:\s*(.+?)\s*\(the gear\)$", "replace": "GPU 名の偽装: $1（歯車アイコン）"},
    {"regex": r"^Inherit the container's\s*\((.+)\)$", "replace": "コンテナの設定を継承（$1）"},
    {"regex": r"^Inherit the container’s\s*\((.+)\)$", "replace": "コンテナの設定を継承（$1）"},
    {"regex": r"^Checked in\s+(\d+)\s*ms$", "replace": "$1 ms で確認完了"},
    {"regex": r"^Bundled:\s*dxvk-nvapi\s+(.+)\.$", "replace": "同梱: dxvk-nvapi $1"},
    {"regex": r"^(.+?)\s*\(not available\)$", "replace": "$1（利用不可）"},
    {"regex": r"^GPU:\s*(.+?)\s*—\s*no tier suggestion$", "replace": "GPU: $1 — 推奨ティアなし"},
    {"regex": r"^(.+?)\s*·\s*auto Tier\s*(.+)$", "replace": "$1 · 自動ティア $2"},
    {"regex": r"^CPU red at:\s*(.+)$", "replace": "CPU 警告温度: $1"},
    {"regex": r"^GPU red at:\s*(.+)$", "replace": "GPU 警告温度: $1"},
    {"regex": r"^Battery red at:\s*(.+)$", "replace": "バッテリー警告温度: $1"},
    {"regex": r"^HUD Scale:\s*(.+)$", "replace": "HUD サイズ: $1"},
    {"regex": r"^HUD Opacity:\s*(.+)$", "replace": "HUD 不透明度: $1"},
    {"regex": r"^HUD outline:\s*(.+)$", "replace": "HUD 輪郭: $1"},
    {"regex": r"^HUD Transparency:\s*(.+)$", "replace": "HUD 透過度: $1"},
    {"regex": r"^Build:\s*(.+)$", "replace": "ビルド: $1"},
    {"regex": r"^ERROR:\s*(.+)$", "replace": "エラー: $1"},
    {"regex": r"^Failed:\s*(.+)$", "replace": "失敗: $1"},

    # ContainersScreen (Layer updates, Duplicate/Remove, Backups)
    {"regex": r'^Duplicate\s+"(.+)"\?$', "replace": "「$1」を複製しますか？"},
    {"regex": r'^Remove\s+"(.+)"\s+permanently\?$', "replace": "「$1」を完全に削除しますか？"},
    {"regex": r'^Remove\s+"(.+)"\?$', "replace": "「$1」を削除しますか？"},
    {"regex": r"^Exported to\s+(.+)$", "replace": "$1 にエクスポートしました"},
    {"regex": r"^Container imported:\s*(.+)$", "replace": "コンテナをインポートしました: $1"},
    {"regex": r"^Download and update layer to\s+(.+)\?$", "replace": "レイヤーを $1 にダウンロードして更新しますか？"},
    {"regex": r"^Update layer to\s+(.+)\?$", "replace": "レイヤーを $1 に更新しますか？"},
    {"regex": r"^Revert layer to\s+(.+)\?$", "replace": "レイヤーを $1 に戻しますか？"},
    {"regex": r"^Download & update to\s+(.+)…$", "replace": "$1 をダウンロードして更新中…"},
    {"regex": r"^Update to\s+(.+)…$", "replace": "$1 に更新中…"},
    {"regex": r"^Update layer →\s*(.+)$", "replace": "レイヤー更新 → $1"},
    {"regex": r"^Download & update layer to\s+(.+)…$", "replace": "レイヤーを $1 にダウンロード＆更新…"},
    {"regex": r"^Update layer to\s+(.+)…$", "replace": "レイヤーを $1 に更新…"},
    {"regex": r"^Revert layer to\s+(.+)…$", "replace": "レイヤーを $1 に戻す…"},
    {"regex": r"^Restoring\s+(.+)…$", "replace": "$1 を復元中…"},
    {"regex": r"^Backing up\s+(.+)…$", "replace": "$1 をバックアップ中…"},
    {"regex": r'^Restored\s+(\d+)\s+files to\s+"(.+)"$', "replace": "$1 個のファイルを「$2」に復元しました"},
    {"regex": r"^Saved\s+(\d+)\s+files\s*→\s*(.+)$", "replace": "$1 個のファイルを保存しました → $2"},
    {"regex": r"^Backed up\s+(\d+)\s+files\s*→\s*(.+)$", "replace": "$1 個のファイルをバックアップしました → $2"},
    {"regex": r"^Backup failed:\s*(.+)$", "replace": "バックアップ失敗: $1"},
    {"regex": r"^Restore failed:\s*(.+)$", "replace": "復元失敗: $1"},
    {"regex": r"^Download failed:\s*(.+)$", "replace": "ダウンロード失敗: $1"},

    # ContentsHub & downloads
    {"regex": r"^(\d+)\s+results?$", "replace": "$1 件の結果"},
    {"regex": r"^No components match\s+[“\"](.+)[”\"]\.$", "replace": "「$1」に一致するコンポーネントはありません。"},
    {"regex": r"^Downloading\s+(\d+)%$", "replace": "ダウンロード中 $1%"},
    {"regex": r"^Already saved to\s+(.+?)\.\s+Long-press to re-download\.$", "replace": "$1 に保存済みです。長押しで再ダウンロードできます。"},
    {"regex": r"^([0-9.]+)\s*([KMG]?B)\s*/\s*([0-9.]+)\s*([KMG]?B)$", "replace": "$1 $2 / $3 $4"},
    {"regex": r"^(\d+)\s+games?$", "replace": "$1 本のゲーム"},
    {"regex": r"^(\d+)\s+containers?$", "replace": "$1 個のコンテナ"},
    {"regex": r"^(\d+)\s+profiles?$", "replace": "$1 個のプロファイル"},

    # PlayerSlotsEditor & Shortcuts
    {"regex": r"^Ignored\s*·\s*on-screen controls$", "replace": "無視 · オンスクリーンコントロール"},
    {"regex": r"^Auto \(assigned by launch order\)\s*·\s*on-screen controls$", "replace": "Auto（起動順で割り当て） · オンスクリーンコントロール"},
    {"regex": r"^Player (\d+)\s*·\s*on-screen controls$", "replace": "Player $1 · オンスクリーンコントロール"},
    {"regex": r"^(.+?)\s*·\s*on-screen controls$", "replace": "$1 · オンスクリーンコントロール"},
    {"regex": r"^(\d+)\s+overridden$", "replace": "$1 件を上書き中"},

    # ContainersScreen layer update / help / revert dialogs
    {"regex": r'^"(.+)" moves from (.+) to (.+)\.$', "replace": "「$1」を $2 から $3 に更新します。"},
    {"regex": r"^The (.+?) layer is not on this device yet: it is downloaded from the catalog(.*?) and installed first, then the container is updated\.$", "replace": "$1 レイヤーはまだこの端末にインストールされていません。先にカタログからダウンロード$2・インストールしてから、コンテナを更新します。"},
    {"regex": r"^The (.+?) layer stays installed and a backup of the registry is taken, so you can revert from this menu\. Make sure nothing is running in this container\.$", "replace": "$1 レイヤーは端末に残され、レジストリのバックアップも作成されるため、このメニューから元に戻すことができます。このコンテナ内で何も実行されていないことを確認してください。"},
    {"regex": r"^The (.+?) layer is no longer installed on this device, so this update cannot be reverted afterwards \(a registry backup is still taken\)\. Make sure nothing is running in this container\.$", "replace": "$1 レイヤーはこの端末からすでに削除されているため、更新後に元へ戻すことはできません（レジストリのバックアップは作成されます）。このコンテナ内で何も実行されていないことを確認してください。"},
    {"regex": r'^A layer is the set of Wine/Proton files a container runs on\. "(.+)" runs on (.+?); a newer (?:build|version) of the same layer, (.+?), is available in the catalog\. The (.+?) layer will be downloaded(.*?) first\.$', "replace": "レイヤーとは、コンテナが動作する Wine/Proton ファイル一式のことです。「$1」は現在 $2 で動作しており、同じレイヤーの新しい版（$3）がカタログに公開されています。先に $4 レイヤーをダウンロード$5します。"},
    {"regex": r'^A layer is the set of Wine/Proton files a container runs on\. "(.+)" runs on (.+?); a newer (?:build|version) of the same layer, (.+?), is installed\.$', "replace": "レイヤーとは、コンテナが動作する Wine/Proton ファイル一式のことです。「$1」は現在 $2 で動作しており、同じレイヤーの新しい版（$3）が端末にインストール済みです。"},
    {"regex": r"^A (.+?) snapshot from an earlier update exists — revert is available in the menu\.$", "replace": "以前の更新時に作成された $1 のスナップショットが残っています — メニューから元に戻せます。"},
    {"regex": r'^"(.+)" goes back from (.+) to (.+)\.$', "replace": "「$1」を $2 から $3 に戻します。"},
    {"regex": r"^The registry is restored from the backup taken before the update \(registry changes made since then are discarded\) and the builtin DLLs are refreshed from the (.+?) layer\. Games, saves, shortcuts and container settings are kept\. Requires the (.+?) layer to still be installed\.$", "replace": "更新前に取得したバックアップからレジストリを復元し（更新後に行ったレジストリ変更は破棄されます）、$1 レイヤーから内蔵 DLL を戻します。ゲーム、セーブデータ、ショートカット、コンテナ設定はそのまま保持されます。実行には $2 レイヤーが端末に残っている必要があります。"},

    # EnvVarsEditor: Prefer game-folder DLLs
    {"regex": r"^Loads the game's own copies of (.+?) instead of Wine's\. Needed by many wrappers and mod loaders\. Graphics DLLs are never included — DXVK/VKD3D own those\. A Microsoft xinput DLL in a game folder does not work under Wine \(it needs a Windows-only driver\); leave it off\.$", "replace": "Wine の代わりに、ゲームフォルダー内の $1 を優先して読み込みます。多くのラッパーや Mod ローダーで必要になります。グラフィックス用 DLL は含まれません（DXVK/VKD3D が管理します）。ゲームフォルダー内の Microsoft 製 xinput DLL は Wine 環境では動作しない（Windows 専用ドライバーが必要）ため、その場合はオフのままにしてください。"},

    # SyncModeSelector: containerSyncHelper (esync / ntsync / wineserver + Greyed reasons)
    {"regex": r"^Checking what (.+?) supports…$", "replace": "$1 の対応状況を確認中…"},
    {"regex": r"^(.+?) isn't in (.+?) — switched back to (.+?) \(layer default\)\.$", "replace": "$1 は $2 に含まれていないため、$3（レイヤーのデフォルト）に戻しました。"},
    {"regex": r"^esync — layer default\. Fast and well tested\.\s*·\s*Greyed:\s*Android blocks fsync\.$", "replace": "esync — レイヤーのデフォルト。高速で動作実績が豊富です。  ·  無効理由: Android は fsync をブロックしています。"},
    {"regex": r"^esync — layer default\. Fast and well tested\.\s*·\s*Greyed:\s*Android blocks fsync;\s*ntsync isn't in (.+)\.$", "replace": "esync — レイヤーのデフォルト。高速で動作実績が豊富です。  ·  無効理由: Android は fsync をブロックしています / $1 は ntsync 非対応。"},
    {"regex": r"^esync — layer default\. Fast and well tested\.\s*·\s*Greyed:\s*Android blocks fsync;\s*(.+)\.$", "replace": "esync — レイヤーのデフォルト。高速で動作実績が豊富です。  ·  無効理由: Android は fsync をブロック / $1。"},
    {"regex": r"^esync — fast and well tested\.\s*·\s*Greyed:\s*Android blocks fsync\.$", "replace": "esync — 高速で動作実績が豊富です。  ·  無効理由: Android は fsync をブロックしています。"},
    {"regex": r"^esync — fast and well tested\.\s*·\s*Greyed:\s*Android blocks fsync;\s*ntsync isn't in (.+)\.$", "replace": "esync — 高速で動作実績が豊富です。  ·  無効理由: Android は fsync をブロックしています / $1 は ntsync 非対応。"},
    {"regex": r"^esync — fast and well tested\.\s*·\s*Greyed:\s*Android blocks fsync;\s*(.+)\.$", "replace": "esync — 高速で動作実績が豊富です。  ·  無効理由: Android は fsync をブロック / $1。"},
    {"regex": r"^ntsync — closest to Windows\. New: try it per game\.\s*·\s*Greyed:\s*Android blocks fsync\.$", "replace": "ntsync — Windows に最も近い同期方式。新規機能のためゲームごとに試してみてください。  ·  無効理由: Android は fsync をブロックしています。"},
    {"regex": r"^ntsync — closest to Windows\. New: try it per game\.\s*·\s*Greyed:\s*Android blocks fsync;\s*(.+)\.$", "replace": "ntsync — Windows に最も近い同期方式。新規機能のためゲームごとに試してみてください。  ·  無効理由: Android は fsync をブロック / $1。"},
    {"regex": r"^wineserver — slowest, most compatible\. For games that misbehave\.\s*·\s*Greyed:\s*Android blocks fsync\.$", "replace": "wineserver — 最も低速ですが互換性が最高です。動作が不安定なゲーム向けです。  ·  無効理由: Android は fsync をブロックしています。"},
    {"regex": r"^wineserver — slowest, most compatible\. For games that misbehave\.\s*·\s*Greyed:\s*Android blocks fsync;\s*ntsync isn't in (.+)\.$", "replace": "wineserver — 最も低速ですが互換性が最高です。動作が不安定なゲーム向けです。  ·  無効理由: Android は fsync をブロックしています / $1 は ntsync 非対応。"},
    {"regex": r"^wineserver — slowest, most compatible\. For games that misbehave\.\s*·\s*Greyed:\s*Android blocks fsync;\s*esync isn't in (.+)\.$", "replace": "wineserver — 最も低速ですが互換性が最高です。動作が不安定なゲーム向けです。  ·  無効理由: Android は fsync をブロックしています / $1 は esync 非対応。"},
    {"regex": r"^wineserver — slowest, most compatible\. For games that misbehave\.\s*·\s*Greyed:\s*Android blocks fsync;\s*ntsync isn't in (.+?);\s*esync isn't in (.+)\.$", "replace": "wineserver — 最も低速ですが互換性が最高です。動作が不安定なゲーム向けです。  ·  無効理由: Android は fsync をブロック / $1 は ntsync・esync 非対応。"},
    {"regex": r"^wineserver — slowest, most compatible\. For games that misbehave\.\s*·\s*Greyed:\s*Android blocks fsync;\s*(.+)\.$", "replace": "wineserver — 最も低速ですが互換性が最高です。動作が不安定なゲーム向けです。  ·  無効理由: Android は fsync をブロック / $1。"},
]


def main():
    seed_path = CLASSIC_DIR / "seed_exact.json"
    exact: dict[str, str] = json.loads(seed_path.read_text(encoding="utf-8"))

    # Add curated exact entries for common UI headers/tabs that must match even if filtered earlier
    curated = {
        "GENERAL": "一般",
        "ENVIRONMENT": "環境変数",
        "DRIVES": "ドライブ",
        "WIN COMPONENTS": "Windows コンポーネント",
        "ADVANCED": "詳細設定",
        "Custom (Pick services individually)": "カスタム（サービスを個別に選択）",
        "Ignored": "無視",
        "Auto (assigned by launch order)": "Auto（起動順で割り当て）",
        "Global defaults": "グローバルデフォルト",
        "-- Disabled --": "-- 無効 --",
        "-- Default --": "-- デフォルト --",
        "About layer updates": "レイヤー更新について",
        "What changes: the Wine/Proton layer files (system32/syswow64 builtin DLLs are refreshed; DXVK, FEX/Box64 and game-installed files are left as they are). Wine finishes its own prefix update on the next launch.": "変更される内容: Wine/Proton レイヤーのファイル（system32/syswow64 の内蔵 DLL が更新されます。DXVK、FEX/Box64、およびゲームがインストールしたファイルはそのまま維持されます）。次回起動時に Wine がプレフィックスの更新を完了します。",
        "What is kept: games, saves, shortcuts and container settings.": "保持される内容: ゲーム、セーブデータ、ショートカット、コンテナ設定。",
        "What the update changes: only Wine's own files inside the container are refreshed to the new version. DXVK, FEX/Box64 and anything a game installed are left as they are; Wine finishes its own prefix update on the next launch.": "更新で変更される内容: コンテナ内の Wine 本体のファイルだけが新しいバージョンに置き換わります。DXVK、FEX/Box64、およびゲームがインストールしたファイルはそのまま維持され、次回起動時に Wine がプレフィックスの更新を完了します。",
        "What is kept: installed games, saves, shortcuts and container settings.": "保持される内容: インストール済みのゲーム、セーブデータ、ショートカット、コンテナ設定。",
        "The old layer stays installed and a backup of the registry is taken first, so \"Revert layer\" is available from this container's menu afterwards.": "古いレイヤーは端末に残され、更新前にレジストリのバックアップも作成されるため、更新後もこのコンテナのメニューから「レイヤーを戻す」を実行できます。",
        "Close the game before updating.": "更新する前にゲームを終了してください。",
        "DirectX 12 fix: For Unreal Engine games run with -dx12 whose HDR option stays greyed out. Safe.": "DirectX 12 fix: -dx12 で起動した Unreal Engine ゲームで HDR オプションがグレーアウトしている場合の修正です。安全に使用できます。",
        "DirectX 11: Experimental. Swaps in dxvk-nvapi for Unreal Engine DirectX 11 games. Pick an NVIDIA GPU in the graphics driver configuration. Turn it off if a game misbehaves. Needs DXVK 2.6 or newer; with an NVIDIA GPU showing, some games also try DLSS or Reflex, which dxvk-nvapi reports as unavailable.": "DirectX 11: 実験的機能です。Unreal Engine の DirectX 11 ゲーム向けに dxvk-nvapi を組み込みます。グラフィックスドライバー設定で NVIDIA GPU を選択してください。動作が不安定な場合はオフにしてください。DXVK 2.6 以降が必要です（NVIDIA GPU を偽装すると一部ゲームが DLSS や Reflex を試行しますが、dxvk-nvapi は非対応として応答します）。",
        "DirectX 11: Experimental. Swaps in dxvk-nvapi for Unreal Engine DirectX 11 games. Pick an NVIDIA GPU in the Wayland driver settings. Turn it off if a game misbehaves. Needs DXVK 2.6 or newer; with an NVIDIA GPU showing, some games also try DLSS or Reflex, which dxvk-nvapi reports as unavailable.": "DirectX 11: 実験的機能です。Unreal Engine の DirectX 11 ゲーム向けに dxvk-nvapi を組み込みます。Wayland ドライバー設定で NVIDIA GPU を選択してください。動作が不安定な場合はオフにしてください。DXVK 2.6 以降が必要です（NVIDIA GPU を偽装すると一部ゲームが DLSS や Reflex を試行しますが、dxvk-nvapi は非対応として応答します）。",
        "HDR output itself needs the Wayland backend, and HDR switched on in the game. Applies from the next launch.": "実際の HDR 出力には Wayland バックエンドと、ゲーム内での HDR 有効化が必要です。次回起動時から反映されます。",
        "Both need HDR output on as well, and HDR switched on in the game. Applies from the next launch.": "いずれも HDR 出力の有効化と、ゲーム内での HDR 有効化が必要です。次回起動時から反映されます。",
        "No NVIDIA GPU is being reported, and Unreal Engine only takes its NVAPI path on one: pick an NVIDIA GPU under GPU name in the graphics driver configuration (the gear). NVIDIA GeForce GTX 1080 matches the generation dxvk-nvapi reports. Optional.": "NVIDIA GPU が認識されていないため、Unreal Engine は NVAPI 経路を使用しません。グラフィックスドライバー設定（歯車アイコン）の GPU 名で NVIDIA GPU を選択してください（NVIDIA GeForce GTX 1080 が dxvk-nvapi の報告世代と一致します・任意）。",
        "No NVIDIA GPU is being reported, and Unreal Engine only takes its NVAPI path on one: pick an NVIDIA GPU under GPU name in the Wayland driver settings (the gear next to Wayland game driver). NVIDIA GeForce GTX 1080 matches the generation dxvk-nvapi reports. Optional.": "NVIDIA GPU が認識されていないため、Unreal Engine は NVAPI 経路を使用しません。Wayland ドライバー設定（Wayland ゲームドライバー横の歯車アイコン）の GPU 名で NVIDIA GPU を選択してください（NVIDIA GeForce GTX 1080 が dxvk-nvapi の報告世代と一致します・任意）。",
        "esync — layer default. Fast and well tested.": "esync — レイヤーのデフォルト。高速で動作実績が豊富です。",
        "esync — fast and well tested.": "esync — 高速で動作実績が豊富です。",
        "ntsync — closest to Windows. New: try it per game.": "ntsync — Windows に最も近い同期方式。新規機能のためゲームごとに試してみてください。",
        "wineserver — slowest, most compatible. For games that misbehave.": "wineserver — 最も低速ですが互換性が最高です。動作が不安定なゲーム向けです。",
        "• Sustained Performance Mode": "• 持続パフォーマンスモード",
        "• Thread Priority Boost": "• スレッド優先度ブースト",
        "• Prefer Big Cores": "• ビッグコアを優先",
        "• Lock GPU to max clock": "• GPU クロックを最大に固定",
        "• CPU governor → performance": "• CPU ガバナー → performance",
        "• Lock CPU frequency to max": "• CPU 周波数を最大に固定",
        "• Keep all cores online": "• すべてのコアをオンラインに維持",
        "• Disable thermal throttling": "• サーマルスロットリングを無効化",
        "• Fan to maximum": "• ファンを最大回転に設定",
        "• Free memory": "• メモリ解放",
    }
    exact.update(curated)

    chunk_files = sorted(CHUNKS_DIR.glob("classic_[0-9][0-9]_ja.json"))
    if len(chunk_files) != 20:
        raise RuntimeError(f"Expected 20 translated chunks, found {len(chunk_files)}")

    added = 0
    for cf in chunk_files:
        items = json.loads(cf.read_text(encoding="utf-8"))
        for obj in items:
            en = obj["en"].strip()
            ja = obj["ja"].strip()
            if not en or not ja:
                continue
            if en in FORBIDDEN_EXACT_KEYS:
                continue
            if en == ja:
                continue
            # Prefer curated/existing translations if already seeded; otherwise insert
            if en not in exact:
                exact[en] = ja
                added += 1

    # Remove any forbidden keys that slipped into seed
    for fk in FORBIDDEN_EXACT_KEYS:
        exact.pop(fk, None)

    # Validate regexes
    for p in DYNAMIC_PATTERNS:
        re.compile(p["regex"])

    OUT_DICT.parent.mkdir(parents=True, exist_ok=True)
    out_obj = {
        "exact": exact,
        "patterns": DYNAMIC_PATTERNS,
    }
    OUT_DICT.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_DICT} ({len(exact)} exact entries [+{added} from Classic chunks], {len(DYNAMIC_PATTERNS)} patterns)")


if __name__ == "__main__":
    main()
