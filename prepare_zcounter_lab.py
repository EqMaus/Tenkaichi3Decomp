#!/usr/bin/env python3
"""Apply the optional hidden Z-Counter laboratory mod to EqMaus/Tenkaichi3Decomp.

Usage (inside a local checkout, no native build required):
    python prepare_zcounter_lab.py

Checks the original code before changing anything, so it fails closed if the
upstream code has changed. Run from any directory: it locates the repository
starting at the current working directory. Files are only written if all
replacement checks succeed.
"""
from pathlib import Path
import sys


def rep(src: str, old: str, new: str, filename: str, tag: str) -> str:
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"{filename}: {tag}: expected 1 match, found {count}. Nothing was written.")
    return src.replace(old, new, 1)


def process(root: Path) -> None:
    paths = [
        'src/battle/btl_input.c',
        'src/battle/btl_char_move.c',
        'port/src/gs/net.c',
        'port/src/gs/ui.cpp',
    ]
    updated = {}
    for name in paths:
        p = root / name
        if not p.is_file():
            raise RuntimeError(f"Missing file {p}; run inside the repo root")
        updated[name] = p.read_text(encoding='utf-8')
    name = paths[0]
    s = updated[name]
    s = rep(s, 'extern s32 BtlChar_TestFlag(BtlInputChr *chr, s32 bit);',
            'extern s32 Port_ZCounterForPlayer(s32 player); /* locally asymmetric experimental rules */\nextern s32 BtlChar_TestFlag(BtlInputChr *chr, s32 bit);', name, 'declaration')
    s = rep(s, '''    case 38:
        result = BtlInput_IsPressed(chr, BTLB_UP);
        break;''',
            '''    case 38:
        if (Port_ZCounterForPlayer(chr->player)) {
            result = BtlInput_IsPressed(chr, BTLB_UP);
        } else {
            result = BtlInput_IsPressed(chr, BTLB_UP) && BtlInput_IsPressed(chr, BTLB_RUSH);
        }
        break;''', name, 'action 38')
    updated[name] = s

    name = paths[1]
    s = updated[name]
    s = rep(s, 'extern s32 BtlInput_TestAction(BtlMoveChr *chr, s32 id, s32 arg);',
            'extern s32 Port_ZCounterForPlayer(s32 player); /* locally asymmetric experimental rules */\nextern s32 BtlInput_TestAction(BtlMoveChr *chr, s32 id, s32 arg);', name, 'declaration')
    s = rep(s, '''        if (BtlInput_TestAction(chr, 0x26, 1)) {
            chr->unk1070 = 4;
        }''',
            '''        if (BtlInput_TestAction(chr, 0x26, 1)) {
            chr->unk1070 = Port_ZCounterForPlayer(chr->player) ? 4 : 1;
        }''', name, 'defence timing')
    updated[name] = s

    name = paths[2]
    s = updated[name]
    s = rep(s, '''#define OPT_MARK 0x4F500000u
static uint32_t sOpts[2];''',
            '''#define OPT_MARK 0x4F500000u
/* Bits 14/15 of the existing per-side options are unused by camera/shake. */
#define ZC_CAPABLE 0x4000u
#define ZC_ENABLED 0x8000u
extern int Port_Setting(const char *name, int def);
static uint32_t sOpts[2];''', name, 'option flags')
    s = rep(s, '''        return OPT_MARK | ((uint32_t)strtoul(carried, NULL, 0) & 0xFFFFu);''',
            '''        return OPT_MARK | ((uint32_t)strtoul(carried, NULL, 0) & 0xFFFFu) | ZC_CAPABLE;''',
            name, 'carried options')
    s = rep(s, '''    return OPT_MARK | (a > 15 ? 0 : a) | (b > 15 ? 0 : b) << 8; /* (anything else: the defaults) */''',
            '''    return OPT_MARK | (a > 15 ? 0 : a) | (b > 15 ? 0 : b) << 8 | ZC_CAPABLE |
           (Port_Setting("zcounter_lab", 0) ? ZC_ENABLED : 0); /* test flag rides with each player's options */''',
            name, 'local options')
    s = rep(s, '''    return sMode > 0;
}

/* A new vertical blank begins''',
            '''    return sMode > 0;
}

/* Local play: only player 1. Online: both clients agree on the enabled side via
   existing per-player handshake. A stock peer does not advertise ZC_CAPABLE:
   fall back to normal rules on BOTH sides, avoiding a desynchronization. */
int Port_ZCounterForPlayer(int player) {
    if (player != 0 && player != 1) { return 0; }
    if (Port_NetActive()) {
        return (sOpts[0] & ZC_CAPABLE) && (sOpts[1] & ZC_CAPABLE) &&
               (sOpts[player] & ZC_ENABLED);
    }
    return player == 0 && Port_Setting("zcounter_lab", 0) != 0;
}

/* A new vertical blank begins''', name, 'per-player query')
    updated[name] = s

    name = paths[3]
    s = updated[name]
    s = rep(s, '''static int sTab;                               // the settings tab that is open (the shoulder buttons go to its neighbours)
''',
            '''static int sTab;                               // the settings tab that is open (the shoulder buttons go to its neighbours)
static bool sZLabVisible;                      // unlock lasts until F1 is closed
static int sZLabCodePos;
''', name, 'secret state')
    s = rep(s, '''    sOpen = open;
    sNet = false;
    sCapKind = 0;''',
            '''    sOpen = open;
    if (!open) { sZLabVisible = false; sZLabCodePos = 0; sTab = 0; }
    sNet = false;
    sCapKind = 0;''', name, 'reset hidden UI')
    s = rep(s, '''static void build(void) {
    PortVideo v, was;''',
            '''/* Type M A U S, Up, Down, Up, Down while F1 is open. No hint in normal UI. */
static void zlab_secret_keys(void) {
    static const ImGuiKey seq[] = {
        ImGuiKey_M, ImGuiKey_A, ImGuiKey_U, ImGuiKey_S,
        ImGuiKey_UpArrow, ImGuiKey_DownArrow, ImGuiKey_UpArrow, ImGuiKey_DownArrow
    };
    for (int i = 0; i < (int)(sizeof(seq) / sizeof(seq[0])); i++) {
        if (ImGui::IsKeyPressed(seq[i], false)) {
            sZLabCodePos = (seq[sZLabCodePos] == seq[i]) ? sZLabCodePos + 1 :
                           (seq[i] == seq[0] ? 1 : 0);
            if (sZLabCodePos == (int)(sizeof(seq) / sizeof(seq[0]))) {
                sZLabVisible = true;
                sZLabCodePos = 0;
            }
            break;
        }
    }
}

static void zlab_tab(void) {
    bool on = Port_Setting("zcounter_lab", 0) != 0;
    ImGui::TextUnformatted("Z-Counter Lab");
    ImGui::Separator();
    if (ImGui::Checkbox("Easy Z-Counter", &on)) {
        Port_SettingSave("zcounter_lab", on ? 1 : 0);
        Port_SettingsWrite();
    }
    ImGui::TextWrapped("Off: Up + Rush, 1 frame. On: Up only, 4 frames, "
                       "for player 1 in local play. In an online session, "
                       "the enabled player's side is synchronized when "
                       "both clients support this experimental rule.");
    ImGui::TextDisabled("Online setting is established when the session starts.");
}

static void build(void) {
    PortVideo v, was;''', name, 'hidden logic')
    s = rep(s, '''    GsGpu_GetSettings(&v);
    was = v;
    if (sCapKind == 2''',
            '''    zlab_secret_keys();
    GsGpu_GetSettings(&v);
    was = v;
    if (sCapKind == 2''', name, 'check secret')
    s = rep(s, '''        sForceTab = (sTab + (ImGui::IsKeyPressed(ImGuiKey_GamepadL1, false) ? 6 : 1)) % 7;''',
            '''        int tabs = sZLabVisible ? 8 : 7;
        sForceTab = (sTab + (ImGui::IsKeyPressed(ImGuiKey_GamepadL1, false) ? tabs - 1 : 1)) % tabs;''',
            name, 'controller tab navigation')
    s = rep(s, '''            if (tab("Misc", 6)) { misc_tab(); ImGui::EndTabItem(); }
            ImGui::EndTabBar();''',
            '''            if (tab("Misc", 6)) { misc_tab(); ImGui::EndTabItem(); }
            if (sZLabVisible && tab("MAUS LAB", 7)) { zlab_tab(); ImGui::EndTabItem(); }
            ImGui::EndTabBar();''', name, 'secret tab')
    updated[name] = s

    for name, content in updated.items():
        (root / name).write_text(content, encoding='utf-8', newline='\n')
        print('Updated:', name)
    print('Done. Commit and push to your fork; then run release.yml in GitHub Actions.')


if __name__ == '__main__':
    try:
        process(Path.cwd())
    except Exception as e:
        print('ERROR:', e, file=sys.stderr)
        sys.exit(1)
