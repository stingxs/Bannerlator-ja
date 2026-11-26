#!/usr/bin/env python3
"""Apply Bannerlator Japanese overlay cleanly onto an upstream checkout before building."""

import argparse
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

OVERLAY_DIR = Path(__file__).resolve().parent

# Dropdown option values & preset names kept in English (labels/headings and help text stay Japanese)
KEEP_ENGLISH_OPTION_STRINGS = {
    # Box64 / FEXCore presets (16)
    "stability", "compatibility", "intermediate", "performance", "performance_tso",
    "performance_mali", "extreme", "extreme_2", "fex_extreme_wn", "fex_extreme_tso_wn",
    "fex_extreme_gn", "fex_performance_x87_full", "fex_unreal_engine_3", "unity",
    "unity_mono_bleeding_edge", "denuvo",
    # Rumble target & motors (8)
    "vibration_mode_off", "vibration_mode_controller", "vibration_mode_device", "vibration_mode_both",
    "rumble_motors_both", "rumble_motors_single", "rumble_motors_both_short", "rumble_motors_single_short",
    # Gyro options (12)
    "gyro_mode_rate", "gyro_mode_orientation", "gyro_target_right_stick", "gyro_target_left_stick",
    "gyro_target_mouse", "gyro_activator_l1", "gyro_activator_l2", "gyro_activator_r1",
    "gyro_activator_r3", "gyro_activator_always", "gyro_activation_hold", "gyro_activation_toggle",
    # Fullscreen & alignment options (17)
    "fullscreen_mode_off", "fullscreen_mode_fit", "fullscreen_mode_stretch", "fullscreen_mode_fill",
    "fullscreen_mode_integer", "fullscreen_mode_default", "fullscreen_mode_off_short",
    "fullscreen_mode_fit_short", "fullscreen_mode_stretch_short", "fullscreen_mode_fill_short",
    "fullscreen_mode_integer_short", "screen_alignment_center", "screen_alignment_top",
    "screen_alignment_bottom", "screen_alignment_center_short", "screen_alignment_top_short",
    "screen_alignment_bottom_short",
    # Frame generation options (7)
    "frame_generation_off", "frame_generation_bionic", "frame_generation_lsfg",
    "frame_generation_lsfg_native", "frame_generation_wfg", "frame_generation_model_default",
    "frame_generation_model_bidirectional",
    # Renderer / present mode / container default options (8)
    "renderer_native_backend_auto", "renderer_native_backend_asr", "renderer_native_backend_flip",
    "renderer_present_mode_fifo", "renderer_present_mode_mailbox", "renderer_present_mode_immediate",
    "use_container_default", "force_ssbs_container_default",
}


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
            if (
                name not in valid_by_tag[e.tag]
                or name in existing_by_tag[e.tag]
                or (e.tag == "string" and name in KEEP_ENGLISH_OPTION_STRINGS)
            ):
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


def install_language_switcher(target_root: Path):
    """Add in-app UI language selector (Auto / English / 日本語) and Android 13+ localeConfig."""
    # 1) Android 13+ per-app language config
    locales_src = OVERLAY_DIR / "res/xml/locales_config.xml"
    if not locales_src.exists():
        raise FileNotFoundError(f"Missing locales_config.xml: {locales_src}")
    locales_dst = target_root / "app/src/main/res/xml/locales_config.xml"
    locales_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(locales_src, locales_dst)

    manifest = target_root / "app/src/main/AndroidManifest.xml"
    mtxt = manifest.read_text(encoding="utf-8")
    if "android:localeConfig" not in mtxt:
        target_attr = 'android:supportsRtl="true"'
        if target_attr not in mtxt:
            raise RuntimeError("Could not find android:supportsRtl in AndroidManifest.xml")
        mtxt = mtxt.replace(
            target_attr,
            'android:supportsRtl="true"\n        android:localeConfig="@xml/locales_config"',
            1,
        )
        manifest.write_text(mtxt, encoding="utf-8")

    # 2) BannerlatorApp: initialize JaOverlay locale before LabLang.init(this)
    app_kt = target_root / "app/src/main/java/com/winlator/star/BannerlatorApp.kt"
    atxt = app_kt.read_text(encoding="utf-8")
    if "JaOverlay.init(this)" not in atxt:
        lab_init = "com.winlator.star.ui.simple.LabLang.init(this)"
        if lab_init not in atxt:
            raise RuntimeError("Could not find LabLang.init(this) in BannerlatorApp.kt")
        atxt = atxt.replace(
            lab_init,
            "com.winlator.star.i18n.JaOverlay.init(this)\n        " + lab_init,
            1,
        )
        app_kt.write_text(atxt, encoding="utf-8")

    # 3) Direct Activity subclasses: apply saved UI locale in attachBaseContext + applyOverrideConfiguration
    base = target_root / "app/src/main/java/com/winlator/star"
    kt_pat = re.compile(
        r"^(\s*(?:(?:public|internal|open)\s+)?class\s+\w+\s*:\s*(?:AppCompatActivity|ComponentActivity|Activity)\(\)[^{]*\{)",
        re.M,
    )
    java_pat = re.compile(
        r"^(\s*(?:public\s+)?class\s+\w+\s+extends\s+(?:AppCompatActivity|ComponentActivity|Activity)\b[^{]*\{)",
        re.M,
    )
    kt_inject = (
        "\n    override fun attachBaseContext(newBase: android.content.Context) {\n"
        "        super.attachBaseContext(com.winlator.star.i18n.JaOverlay.wrapContext(newBase))\n"
        "    }\n\n"
        "    override fun applyOverrideConfiguration(overrideConfiguration: android.content.res.Configuration?) {\n"
        "        if (overrideConfiguration != null) {\n"
        "            com.winlator.star.i18n.JaOverlay.applyLocaleToConfig(overrideConfiguration)\n"
        "        }\n"
        "        super.applyOverrideConfiguration(overrideConfiguration)\n"
        "    }"
    )
    java_inject = (
        "\n    @Override\n"
        "    protected void attachBaseContext(android.content.Context newBase) {\n"
        "        super.attachBaseContext(com.winlator.star.i18n.JaOverlay.wrapContext(newBase));\n"
        "    }\n\n"
        "    @Override\n"
        "    public void applyOverrideConfiguration(android.content.res.Configuration overrideConfiguration) {\n"
        "        if (overrideConfiguration != null) {\n"
        "            com.winlator.star.i18n.JaOverlay.applyLocaleToConfig(overrideConfiguration);\n"
        "        }\n"
        "        super.applyOverrideConfiguration(overrideConfiguration);\n"
        "    }"
    )
    kt_patched = 0
    java_patched = 0
    for p in sorted(base.rglob("*")):
        if p.suffix not in (".kt", ".java") or not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "attachBaseContext" in txt:
            continue
        if p.suffix == ".kt":
            new_txt, n = kt_pat.subn(lambda m: m.group(1) + kt_inject, txt, count=1)
            if n:
                p.write_text(new_txt, encoding="utf-8")
                kt_patched += 1
        else:
            new_txt, n = java_pat.subn(lambda m: m.group(1) + java_inject, txt, count=1)
            if n:
                p.write_text(new_txt, encoding="utf-8")
                java_patched += 1

    if kt_patched < 30 or java_patched < 5:
        raise RuntimeError(f"Unexpected Activity patch counts: kt={kt_patched}, java={java_patched}")

    # 4) Classic AppearanceScreen.kt: add UI Language switcher
    appearance = base / "ui/screens/AppearanceScreen.kt"
    ap_txt = appearance.read_text(encoding="utf-8")
    ap_anchor = (
        "        Spacer(Modifier.height(4.dp))\n"
        "        Box(Modifier.fillMaxWidth().height(1.dp).background(Divider))\n\n"
        "        // ── Preset themes"
    )
    if ap_anchor not in ap_txt:
        raise RuntimeError("Could not find Theme Presets anchor in AppearanceScreen.kt")
    ui_lang_section = """        Spacer(Modifier.height(4.dp))
        Box(Modifier.fillMaxWidth().height(1.dp).background(Divider))

        // ── UI Language ──────────────────────────────────────────────────
        SectionLabel("UI Language")
        Text(
            text = "Choose the display language for the UI. Auto follows your device language. Changing this restarts Bannerlator.",
            color = OnSurfaceVariant,
            fontSize = 12.sp,
        )
        Spacer(Modifier.height(6.dp))
        val langOptions = listOf("" to "Auto", "en" to "English", "ja" to "日本語")
        val currentLangTag = remember { com.winlator.star.i18n.JaOverlay.getLanguageTag(context) }
        val selectedLangIdx = langOptions.indexOfFirst { (tag, _) ->
            if (tag.isEmpty()) currentLangTag.isEmpty()
            else currentLangTag.equals(tag, ignoreCase = true) || currentLangTag.startsWith("$tag-", ignoreCase = true)
        }.let { if (it >= 0) it else 0 }
        var pendingLangTag by remember { mutableStateOf<String?>(null) }
        SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
            langOptions.forEachIndexed { index, (tag, label) ->
                SegmentedButton(
                    selected = selectedLangIdx == index,
                    onClick = {
                        if (selectedLangIdx != index) pendingLangTag = tag
                    },
                    shape = SegmentedButtonDefaults.itemShape(index, langOptions.size),
                ) { androidx.compose.material3.Text(label) }
            }
        }
        pendingLangTag?.let { newTag ->
            androidx.compose.material3.AlertDialog(
                onDismissRequest = { pendingLangTag = null },
                title = { Text("Switch UI language?") },
                text = { Text("Bannerlator restarts to switch the language.") },
                confirmButton = {
                    androidx.compose.material3.TextButton(onClick = {
                        pendingLangTag = null
                        com.winlator.star.i18n.JaOverlay.findActivity(context)?.let { act ->
                            com.winlator.star.i18n.JaOverlay.setAppLanguage(act, newTag)
                        }
                    }) { Text("Restart") }
                },
                dismissButton = {
                    androidx.compose.material3.TextButton(onClick = { pendingLangTag = null }) {
                        Text("Cancel")
                    }
                },
            )
        }

        Spacer(Modifier.height(4.dp))
        Box(Modifier.fillMaxWidth().height(1.dp).background(Divider))

        // ── Preset themes"""
    appearance.write_text(ap_txt.replace(ap_anchor, ui_lang_section, 1), encoding="utf-8")
    print(f"Installed UI language switcher (Activities patched: kt={kt_patched}, java={java_patched})")


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
    install_language_switcher(target_root)
    print("Japanese overlay applied successfully.")


if __name__ == "__main__":
    main()
