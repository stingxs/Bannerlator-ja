#!/usr/bin/env python3
"""Extract Classic UI hardcoded strings and build seed dictionary from existing Japanese XMLs."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo/
WORKSPACE = ROOT.parent  # Bannerlator workspace/
JA_OVERLAY = ROOT / "ja-overlay"
TOOLS_DIR = JA_OVERLAY / "tools"

SKIP_VALUES_EXACT = {
    "", " ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "...", "OK", "ID", "URL", "FPS", "GPU", "CPU", "RAM", "VRAM",
    "X11", "DLL", "API", "HUD", "HDR", "HDR10", "SDR", "USB", "DPI",
    "MB", "GB", "KB", "Hz", "ms", "x86", "x64", "ARM64", "WoW64",
    "DXVK", "VKD3D", "D7VK", "Wine", "Proton", "Box64", "FEXCore",
    "Turnip", "Zink", "VirGL", "Vulkan", "OpenGL", "Wayland", "yserver",
    "Steam", "Epic", "GOG", "Amazon", "Xbox", "Gamescope", "MangoHud",
    "C:", "D:", "Z:", "E:", "F:",
}

ENV_KEY_RE = re.compile(r"^[A-Z0-9_]{2,}$")
CAMEL_IDENT_RE = re.compile(r"^[a-z][a-zA-Z0-9_]*$")
SNAKE_IDENT_RE = re.compile(r"^[a-z0-9_./:-]+$")
PATH_OR_URL_RE = re.compile(r"^(?:https?://|file://|/|~|\./|\.\./|[A-Za-z]:\\|\*[A-Za-z0-9.*]+)")
HEX_OR_NUM_RE = re.compile(r"^(?:#[0-9a-fA-F]{3,8}|[0-9.,:%+\-xX/ ]+)$")
HAS_ALPHA_RE = re.compile(r"[A-Za-z]{2,}")


def unescape_android_xml(s: str) -> str:
    s = s.replace("\\n", "\n").replace("\\t", "\t").replace("\\'", "'").replace('\\"', '"')
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return re.sub(r"\s+", " ", s) if "\n" not in s else s


def inner_text(elem: ET.Element) -> str:
    parts = [elem.text or ""]
    for c in elem:
        parts.append(ET.tostring(c, encoding="unicode"))
    return "".join(parts)


def load_xml_pairs(en_path: Path, ja_path: Path) -> dict[str, str]:
    if not en_path.exists() or not ja_path.exists():
        return {}
    en_root = ET.parse(en_path).getroot()
    ja_root = ET.parse(ja_path).getroot()
    en_map = {
        e.attrib["name"]: inner_text(e)
        for e in en_root
        if e.tag == "string" and "name" in e.attrib and len(e) == 0
    }
    ja_map = {
        e.attrib["name"]: inner_text(e)
        for e in ja_root
        if e.tag == "string" and "name" in e.attrib and len(e) == 0
    }
    pairs = {}
    for k, en_v in en_map.items():
        if k in ja_map:
            en_clean = unescape_android_xml(en_v).strip()
            ja_clean = unescape_android_xml(ja_map[k]).strip()
            if en_clean and ja_clean and en_clean not in SKIP_VALUES_EXACT and "%" not in en_clean:
                pairs[en_clean] = ja_clean
    return pairs


def is_likely_ui_text(s: str) -> bool:
    st = s.strip()
    if not st or st in SKIP_VALUES_EXACT:
        return False
    if len(st) <= 1:
        return False
    if not HAS_ALPHA_RE.search(st):
        return False
    if ENV_KEY_RE.match(st):
        return False
    if CAMEL_IDENT_RE.match(st):
        return False
    if SNAKE_IDENT_RE.match(st) and " " not in st:
        return False
    if PATH_OR_URL_RE.match(st):
        return False
    if HEX_OR_NUM_RE.match(st):
        return False
    if st.startswith(("com.", "org.", "android.", "androidx.", "java.", "kotlin.", "application/", "image/", "text/", "video/", "audio/", "(?")):
        return False
    if re.match(r"^[A-Za-z0-9_.-]+=[A-Za-z0-9_.,:-]*$", st) and " " not in st:
        return False
    if re.match(r"^[A-Z][a-zA-Z0-9]*(?:Activity|Fragment|ViewModel|Dialog|Manager|Importer|Helper|Provider|Service|Receiver|Adapter|Worker)$", st):
        return False
    if st.endswith((".exe", ".dll", ".so", ".apk", ".tzst", ".zst", ".zip", ".json", ".xml", ".png", ".jpg", ".txt", ".log", ".ini", ".cfg", ".conf", ".wcp")):
        return False
    # Reject single lowercase technical tokens or placeholders
    if " " not in st and len(st) <= 3 and st.islower():
        return False
    return True


def scan_kotlin_strings(text: str) -> tuple[list[str], list[str]]:
    """Parse Kotlin string literals (including '+' concatenations) outside comments and triple-quoted raw strings."""
    static_strings = []
    template_strings = []
    n = len(text)
    i = 0
    tokens = []  # list of (kind: 'str'|'tpl'|'plus'|'other', value, line)
    line = 1

    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        # Line comment
        if text.startswith("//", i):
            nl = text.find("\n", i)
            i = n if nl == -1 else nl
            continue
        # Block comment
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                break
            line += text.count("\n", i, end + 2)
            i = end + 2
            continue
        # Triple-quoted string (skip or record)
        if text.startswith('"""', i):
            end = text.find('"""', i + 3)
            if end == -1:
                break
            line += text.count("\n", i, end + 3)
            i = end + 3
            tokens.append(("other", "", line))
            continue
        # Char literal
        if c == "'":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                elif text[j] == "'":
                    j += 1
                    break
                else:
                    j += 1
            i = j
            tokens.append(("other", "", line))
            continue
        # Standard string literal
        if c == '"':
            j = i + 1
            buf = []
            has_tpl = False
            while j < n:
                ch = text[j]
                if ch == '"':
                    j += 1
                    break
                if ch == "\n":
                    line += 1
                    j += 1
                    break
                if ch == "\\":
                    if j + 1 < n:
                        nxt = text[j + 1]
                        if nxt == "n":
                            buf.append("\n")
                            j += 2
                            continue
                        elif nxt == "t":
                            buf.append("\t")
                            j += 2
                            continue
                        elif nxt == "r":
                            buf.append("\r")
                            j += 2
                            continue
                        elif nxt == "u" and j + 6 <= n:
                            try:
                                buf.append(chr(int(text[j + 2:j + 6], 16)))
                                j += 6
                                continue
                            except ValueError:
                                pass
                        buf.append(nxt)
                        j += 2
                        continue
                if ch == "$" and j + 1 < n and (text[j + 1] == "{" or text[j + 1].isalpha() or text[j + 1] == "_"):
                    has_tpl = True
                    if text[j + 1] == "{":
                        depth = 1
                        k = j + 2
                        while k < n and depth > 0:
                            if text[k] == "{":
                                depth += 1
                            elif text[k] == "}":
                                depth -= 1
                            k += 1
                        buf.append(text[j:k])
                        j = k
                        continue
                    else:
                        k = j + 1
                        while k < n and (text[k].isalnum() or text[k] == "_"):
                            k += 1
                        buf.append(text[j:k])
                        j = k
                        continue
                buf.append(ch)
                j += 1
            val = "".join(buf)
            tokens.append(("tpl" if has_tpl else "str", val, line))
            i = j
            continue
        if c == "+":
            tokens.append(("plus", "+", line))
            i += 1
            continue
        tokens.append(("other", c, line))
        i += 1

    # Merge adjacent str/tpl tokens joined by '+'
    idx = 0
    while idx < len(tokens):
        kind, val, ln = tokens[idx]
        if kind in ("str", "tpl"):
            merged_val = val
            merged_tpl = kind == "tpl"
            k = idx
            while k + 2 < len(tokens) and tokens[k + 1][0] == "plus" and tokens[k + 2][0] in ("str", "tpl"):
                merged_val += tokens[k + 2][1]
                if tokens[k + 2][0] == "tpl":
                    merged_tpl = True
                k += 2
            if merged_tpl:
                template_strings.append(merged_val)
            else:
                static_strings.append(merged_val)
            idx = k + 1
        else:
            idx += 1

    return static_strings, template_strings


def main():
    seed_exact = {}
    # 1) Lab pairs (about 1900)
    seed_exact.update(load_xml_pairs(
        ROOT / "app/src/main/res/values/strings_lab.xml",
        ROOT / "app/src/main/res/values-ja/strings_lab.xml",
    ))
    seed_exact.update(load_xml_pairs(
        ROOT / "app/src/main/res/values/strings_lab.xml",
        JA_OVERLAY / "res/values-ja/strings_lab_missing.xml",
    ))
    # 2) Classic strings pairs (about 1460)
    if (WORKSPACE / "upstream/values/strings.xml").exists():
        seed_exact.update(load_xml_pairs(
            WORKSPACE / "upstream/values/strings.xml",
            JA_OVERLAY / "res/values-ja/strings.xml",
        ))
        seed_exact.update(load_xml_pairs(
            WORKSPACE / "upstream/values/strings_xmb_downloads.xml",
            JA_OVERLAY / "res/values-ja/strings_xmb_downloads.xml",
        ))
        seed_exact.update(load_xml_pairs(
            WORKSPACE / "upstream/values/strings_xmb_friends.xml",
            JA_OVERLAY / "res/values-ja/strings_xmb_friends.xml",
        ))

    print(f"Seed exact dictionary entries: {len(seed_exact)}")

    java_base = ROOT / "app/src/main/java/com/winlator/star"
    target_files = []
    for p in sorted(java_base.rglob("*.kt")):
        rel = str(p.relative_to(java_base)).replace("\\", "/")
        if rel.startswith("ui/simple/") or rel.startswith("i18n/"):
            continue
        if rel.startswith("ui/") or rel.startswith("store/") or rel in {
            "ControlsEditorDialogs.kt",
            "ControlsEditorSettingsPane.kt",
            "ExternalControllerBindingsActivity.kt",
            "FilePickerActivity.kt",
            "MainActivity.kt",
            "OpenExeActivity.kt",
            "ShortcutPickerActivity.kt",
            "UnpackArchiveActivity.kt",
            "contents/WrapperSettingsDictionary.kt",
        }:
            # Exclude ui/deck/ unless needed; focus on Classic, shared components, dialogs, overlays, files, UpdateCards, stores
            if rel.startswith("ui/deck/"):
                continue
            target_files.append((rel, p))

    print(f"Scanning {len(target_files)} Kotlin UI files...")

    # Also focus only on strings that are plausibly passed to UI (anywhere in files importing material3.Text or Text()/help/title/label)
    extracted_static = {}
    extracted_templates = {}

    # Priority order: core Classic screens/components first, then stores
    for rel, p in target_files:
        txt = p.read_text(encoding="utf-8", errors="replace")
        # Only scan files that actually use Compose Text or define UI labels/help
        if "Text(" not in txt and "FieldSetLabel" not in txt and "Glossary" not in rel and "WrapperSettingsDictionary" not in rel:
            continue
        statics, tpls = scan_kotlin_strings(txt)
        for s in statics:
            st = s.strip()
            if not is_likely_ui_text(st):
                continue
            if st in seed_exact:
                continue
            extracted_static.setdefault(st, []).append(rel)
        for t in tpls:
            tt = t.strip()
            if len(tt) >= 4 and HAS_ALPHA_RE.search(tt):
                extracted_templates.setdefault(tt, []).append(rel)

    print(f"Unique untranslated static UI string candidates: {len(extracted_static)}")
    print(f"Unique template UI string candidates: {len(extracted_templates)}")

    # Breakdown by top area
    core_keys = [k for k, v in extracted_static.items() if not all(f.startswith("store/") for f in v)]
    store_keys = [k for k, v in extracted_static.items() if all(f.startswith("store/") for f in v)]
    print(f"  Core Classic/Shared candidates: {len(core_keys)}")
    print(f"  Store-only candidates: {len(store_keys)}")

    out_dir = WORKSPACE / "translations" / "classic"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "seed_exact.json").write_text(json.dumps(seed_exact, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save templates from core files so we can craft clean regex patterns
    core_tpls = [
        {"en_template": k, "files": sorted(set(v))}
        for k, v in extracted_templates.items()
        if not all(f.startswith("store/") for f in v)
    ]
    (out_dir / "core_templates.json").write_text(json.dumps(core_tpls, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save all static candidates (core first, then store) into chunks of 220
    ordered = [{"en": k, "files": sorted(set(extracted_static[k]))[:3]} for k in core_keys + store_keys]
    (out_dir / "all_candidates.json").write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")

    chunk_size = 220
    chunks_dir = out_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    for old in chunks_dir.glob("classic_*.json"):
        old.unlink()
    for idx in range(0, len(ordered), chunk_size):
        chunk = ordered[idx:idx + chunk_size]
        cpath = chunks_dir / f"classic_{(idx // chunk_size) + 1:02d}.json"
        cpath.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {((len(ordered) - 1) // chunk_size) + 1 if ordered else 0} chunks to {chunks_dir}")


if __name__ == "__main__":
    main()
