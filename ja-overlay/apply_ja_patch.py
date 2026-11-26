#!/usr/bin/env python3
"""Apply Bannerlator Japanese overlay cleanly onto an upstream checkout before building."""

import argparse
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

OVERLAY_DIR = Path(__file__).resolve().parent


def filter_xml_against_default(src_xml: Path, default_xmls: list[Path], existing_ja_xml: Path | None = None) -> str:
    """Keep only resource items present in default values/ and not already defined in existing values-ja/."""
    valid_by_tag: dict[str, set[str]] = {"string": set(), "plurals": set(), "string-array": set()}
    for dpath in default_xmls:
        if not dpath.exists():
            continue
        root = ET.parse(dpath).getroot()
        for e in root:
            if e.tag in valid_by_tag and "name" in e.attrib:
                valid_by_tag[e.tag].add(e.attrib["name"])

    existing_by_tag: dict[str, set[str]] = {"string": set(), "plurals": set(), "string-array": set()}
    if existing_ja_xml is not None and existing_ja_xml.exists():
        root = ET.parse(existing_ja_xml).getroot()
        for e in root:
            if e.tag in existing_by_tag and "name" in e.attrib:
                existing_by_tag[e.tag].add(e.attrib["name"])

    src_text = src_xml.read_text(encoding="utf-8")
    src_root = ET.fromstring(src_text)
    drop_names = set()
    for e in src_root:
        if e.tag in valid_by_tag and "name" in e.attrib:
            name = e.attrib["name"]
            if name not in valid_by_tag[e.tag] or name in existing_by_tag[e.tag]:
                drop_names.add((e.tag, name))

    if not drop_names:
        return src_text

    # Remove dropped blocks from raw text to preserve exact Android XML escapes
    out_text = src_text
    for tag, name in drop_names:
        pattern = re.compile(rf'(?ms)^[ \t]*<{tag}\s+[^>]*name="{re.escape(name)}"[^>]*>.*?</{tag}>\r?\n?')
        out_text = pattern.sub("", out_text)
    ET.fromstring(out_text)
    print(f"  Filtered {len(drop_names)} obsolete/already-translated items from {src_xml.name}")
    return out_text


def patch_updater(target_root: Path, repo_slug: str):
    um = target_root / "app/src/main/java/com/winlator/star/core/UpdateManager.kt"
    text = um.read_text(encoding="utf-8")
    pattern = r'private\s+const\s+val\s+REPO\s*=\s*"[^"]+"'
    if not re.search(pattern, text):
        raise RuntimeError("Could not find REPO constant in UpdateManager.kt")
    new_text = re.sub(pattern, f'private const val REPO = "{repo_slug}"', text, count=1)
    um.write_text(new_text, encoding="utf-8")
    print(f"Patched UpdateManager.kt REPO -> {repo_slug}")


def patch_version_code(target_root: Path, offset: int):
    if offset == 0:
        return
    bg = target_root / "app/build.gradle"
    text = bg.read_text(encoding="utf-8")
    m = re.search(r'^(\s*versionCode\s+)(\d+)\b', text, re.M)
    if not m:
        raise RuntimeError("Could not find versionCode in app/build.gradle")
    old_code = int(m.group(2))
    new_code = old_code + offset
    new_text = text[:m.start()] + f"{m.group(1)}{new_code}" + text[m.end():]
    bg.write_text(new_text, encoding="utf-8")
    print(f"Bumped versionCode: {old_code} -> {new_code} (+{offset})")


def install_resources_and_assets(target_root: Path):
    res_values = target_root / "app/src/main/res/values"
    res_ja = target_root / "app/src/main/res/values-ja"
    res_ja.mkdir(parents=True, exist_ok=True)

    default_xmls = [
        res_values / "strings.xml",
        res_values / "strings_lab.xml",
        res_values / "strings_xmb_downloads.xml",
        res_values / "strings_xmb_friends.xml",
    ]

    for xml_name in ["strings.xml", "strings_xmb_downloads.xml", "strings_xmb_friends.xml"]:
        src = OVERLAY_DIR / "res/values-ja" / xml_name
        if src.exists():
            filtered = filter_xml_against_default(src, default_xmls)
            (res_ja / xml_name).write_text(filtered, encoding="utf-8")
            print(f"Installed values-ja/{xml_name}")

    lab_missing = OVERLAY_DIR / "res/values-ja/strings_lab_missing.xml"
    if lab_missing.exists():
        filtered = filter_xml_against_default(
            lab_missing,
            [res_values / "strings_lab.xml"],
            existing_ja_xml=res_ja / "strings_lab.xml",
        )
        (res_ja / "strings_lab_missing.xml").write_text(filtered, encoding="utf-8")
        print("Installed values-ja/strings_lab_missing.xml")

    assets_dir = target_root / "app/src/main/assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    dict_src = OVERLAY_DIR / "assets/ja_classic_dict.json"
    if not dict_src.exists():
        raise FileNotFoundError(f"Missing dictionary: {dict_src}")
    shutil.copy2(dict_src, assets_dir / "ja_classic_dict.json")
    print("Installed assets/ja_classic_dict.json")

    i18n_dest = target_root / "app/src/main/java/com/winlator/star/i18n/JaOverlay.kt"
    i18n_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OVERLAY_DIR / "src/com/winlator/star/i18n/JaOverlay.kt", i18n_dest)
    print("Installed JaOverlay.kt")


def rewrite_compose_text_imports(target_root: Path):
    base = target_root / "app/src/main/java/com/winlator/star"
    rewritten = 0
    for p in sorted(base.rglob("*.kt")):
        rel = str(p.relative_to(base)).replace("\\", "/")
        if rel.startswith("ui/simple/") or rel.startswith("i18n/"):
            continue
        txt = p.read_text(encoding="utf-8")
        if re.search(r"\bfun\s+Text\s*\(", txt) or re.search(r"import\s+androidx\.compose\.material3\.Text\s+as\b", txt):
            continue
        if "com.winlator.star.i18n.Text" in txt:
            continue

        new_txt = txt
        if re.search(r"^import\s+androidx\.compose\.material3\.Text\s*$", txt, re.M):
            new_txt = re.sub(
                r"^import\s+androidx\.compose\.material3\.Text\s*$",
                "import com.winlator.star.i18n.Text",
                txt,
                flags=re.M,
            )
        elif "import androidx.compose.material3.*" in txt and re.search(r"(?<![A-Za-z0-9_.])Text\s*\(", txt):
            new_txt = txt.replace(
                "import androidx.compose.material3.*",
                "import androidx.compose.material3.*\nimport com.winlator.star.i18n.Text",
                1,
            )

        if new_txt != txt:
            p.write_text(new_txt, encoding="utf-8")
            rewritten += 1

    # Also translate HelpTextDialog raw HTML strings before htmlToAnnotated() parses spans
    help_dlg = base / "ui/screens/HelpDialog.kt"
    if help_dlg.exists():
        ht = help_dlg.read_text(encoding="utf-8")
        target_line = "val annotated = remember(text) { htmlToAnnotated(text) }"
        if target_line in ht:
            ht = ht.replace(
                target_line,
                "val context = LocalContext.current\n    val annotated = remember(text) { htmlToAnnotated(com.winlator.star.i18n.JaOverlay.tr(context, text)) }",
                1,
            )
            help_dlg.write_text(ht, encoding="utf-8")
            print("Patched HelpDialog.kt HelpTextDialog()")

    print(f"Rewrote Compose Text imports in {rewritten} Kotlin files")


def replace_exact_once(path: Path, old: str, new: str, label: str):
    txt = path.read_text(encoding="utf-8")
    if old not in txt:
        raise RuntimeError(f"keep_raw_ui_values target not found in {path.name}: {label}")
    path.write_text(txt.replace(old, new, 1), encoding="utf-8")


def keep_raw_ui_values(target_root: Path):
    """Keep dropdown option texts and file/folder names untranslated (use material3.Text directly)."""
    base = target_root / "app/src/main/java/com/winlator/star"

    # 1) Dropdown choice items (keep field labels/headings translated; keep option values raw English)
    cds = base / "ui/screens/ContainerDetailScreen.kt"
    cds_txt = cds.read_text(encoding="utf-8")
    cds_new, cds_cnt = re.subn(
        r"DropdownMenuItem\(\s*text = \{ Text\(opt\) \}",
        "DropdownMenuItem(\n                    text = { androidx.compose.material3.Text(opt) }",
        cds_txt,
    )
    if cds_cnt < 2:
        # Handle single-line or multi-line formatting safely
        cds_new, cds_cnt = re.subn(
            r"text = \{ Text\(opt\) \}",
            "text = { androidx.compose.material3.Text(opt) }",
            cds_txt,
        )
    if cds_cnt == 0:
        raise RuntimeError("No DropdownMenuItem Text(opt) found in ContainerDetailScreen.kt")
    cds.write_text(cds_new, encoding="utf-8")

    replace_exact_once(
        base / "ui/components/PlayerSlotsEditor.kt",
        "DropdownMenuItem(text = { Text(label) }, onClick = {",
        "DropdownMenuItem(text = { androidx.compose.material3.Text(label) }, onClick = {",
        "PlayerSlotsEditor DropdownMenuItem",
    )
    replace_exact_once(
        base / "ControlsEditorSettingsPane.kt",
        "DropdownMenuItem(\n                        text = {\n                            Text(\n                                text = option,",
        "DropdownMenuItem(\n                        text = {\n                            androidx.compose.material3.Text(\n                                text = option,",
        "ControlsEditorSettingsPane SettingSpinner",
    )
    replace_exact_once(
        base / "ui/dialogs/InputControlsDialog.kt",
        "DropdownMenuItem(\n                                text = { Text(label) },",
        "DropdownMenuItem(\n                                text = { androidx.compose.material3.Text(label) },",
        "InputControlsDialog DropdownMenuItem",
    )
    replace_exact_once(
        base / "ui/dialogs/ScreenEffectsDialog.kt",
        "DropdownMenuItem(\n                                text = { Text(label) },",
        "DropdownMenuItem(\n                                text = { androidx.compose.material3.Text(label) },",
        "ScreenEffectsDialog DropdownMenuItem",
    )

    saves = base / "ui/screens/SavesScreen.kt"
    saves_txt = saves.read_text(encoding="utf-8")
    saves_new, saves_cnt = re.subn(
        r"text = \{ Text\(c\.getName\(\)\) \}",
        "text = { androidx.compose.material3.Text(c.getName()) }",
        saves_txt,
    )
    if saves_cnt == 0:
        raise RuntimeError("No Text(c.getName()) found in SavesScreen.kt")
    saves.write_text(saves_new, encoding="utf-8")

    # Box64 / FEXCore preset pickers in SettingsScreen.kt
    ss = base / "ui/screens/SettingsScreen.kt"
    ss_txt = ss.read_text(encoding="utf-8")
    ss_txt, ss_preset_cnt = re.subn(
        r"text = \{ Text\(preset\.name\) \}",
        "text = { androidx.compose.material3.Text(preset.name) }",
        ss_txt,
    )
    ss_txt, ss_btn_cnt = re.subn(
        r"Text\(label, color = MaterialTheme\.colorScheme\.onSurface\)",
        "androidx.compose.material3.Text(label, color = MaterialTheme.colorScheme.onSurface)",
        ss_txt,
    )
    if ss_preset_cnt == 0 or ss_btn_cnt == 0:
        raise RuntimeError("Preset picker Text targets not found in SettingsScreen.kt")
    ss.write_text(ss_txt, encoding="utf-8")

    # 2) File browser / picker real directory and file names (keep "ホーム > 内部" crumbs, keep folder names raw)
    fm_ui = base / "ui/files/FmUi.kt"
    replace_exact_once(
        fm_ui,
        "            Column(Modifier.weight(1f)) {\n                Text(\n                    item.name,",
        "            Column(Modifier.weight(1f)) {\n                androidx.compose.material3.Text(\n                    item.name,",
        "FmUi FmRow item.name",
    )
    replace_exact_once(
        fm_ui,
        "            Spacer(Modifier.height(if (dense) 3.dp else 6.dp))\n            Text(\n                item.name,",
        "            Spacer(Modifier.height(if (dense) 3.dp else 6.dp))\n            androidx.compose.material3.Text(\n                item.name,",
        "FmUi FmTile item.name",
    )
    replace_exact_once(
        fm_ui,
        "        segments.forEachIndexed { i, (label, go) ->\n            val last = i == segments.lastIndex\n            Text(\n                label,",
        "        segments.forEachIndexed { i, (label, go) ->\n            val last = i == segments.lastIndex\n            if (i <= 1) Text(\n                label,\n                color = if (last) cs.onSurface else cs.primary,\n                fontSize = if (dense) 12.sp else 13.sp,\n                fontWeight = if (last) FontWeight.SemiBold else FontWeight.Medium,\n                maxLines = 1,\n                modifier = Modifier\n                    .clip(RoundedCornerShape(8.dp))\n                    .clickable(enabled = !last, onClick = go)\n                    .padding(horizontal = 6.dp, vertical = vPad),\n            ) else androidx.compose.material3.Text(\n                label,",
        "FmUi FmCrumbs folder names",
    )
    replace_exact_once(
        base / "ui/files/FmDialogs.kt",
        "title = { Text(file.name.ifBlank { file.absolutePath }, maxLines = 2, overflow = TextOverflow.Ellipsis) },",
        "title = { androidx.compose.material3.Text(file.name.ifBlank { file.absolutePath }, maxLines = 2, overflow = TextOverflow.Ellipsis) },",
        "FmDialogs title",
    )
    replace_exact_once(
        base / "ui/files/FmNetDialogs.kt",
        "title = { Text(item.name, maxLines = 2, overflow = TextOverflow.Ellipsis) },",
        "title = { androidx.compose.material3.Text(item.name, maxLines = 2, overflow = TextOverflow.Ellipsis) },",
        "FmNetDialogs title",
    )
    replace_exact_once(
        base / "ui/files/TextEditorScreen.kt",
        "text = { Text(file.name) }",
        "text = { androidx.compose.material3.Text(file.name) }",
        "TextEditorScreen title",
    )

    print(
        f"Kept raw UI values: ContainerDetail={cds_cnt}, Saves={saves_cnt}, "
        f"SettingsPresets={ss_preset_cnt}+{ss_btn_cnt}, plus PlayerSlots/Controls/Dialogs/Files"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default=".", help="Root of upstream Bannerlator checkout")
    parser.add_argument("--repo", required=True, help="Fork owner/repo for UpdateManager")
    parser.add_argument("--version-code-offset", type=int, default=0)
    args = parser.parse_args()

    target_root = Path(args.target).resolve()
    patch_updater(target_root, args.repo)
    patch_version_code(target_root, args.version_code_offset)
    install_resources_and_assets(target_root)
    rewrite_compose_text_imports(target_root)
    keep_raw_ui_values(target_root)
    print("Japanese overlay applied successfully.")


if __name__ == "__main__":
    main()
