#!/usr/bin/env python3
"""Input Viewer v1 hotfix for Tenkaichi3Decomp.

Run in GitHub Actions AFTER prepare_zcounter_lab.py and prepare_input_viewer.py.
- Allow mouse events to reach ImGui while F1 is closed, so title bars can be dragged.
- Prevent the live viewer window from reacting to keyboard/gamepad navigation or scrolling.
- Preserve its saved X/Y position and all existing gameplay/network logic.
"""
from pathlib import Path

file = Path(__file__).resolve().parent / "port/src/gs/ui.cpp"
s = file.read_text(encoding="utf-8")
marker = "BT3_INPUT_VIEWER_DRAG_FIX_V2"
if marker in s:
    print("Input Viewer drag hotfix already applied")
    raise SystemExit(0)
if "BT3_INPUT_VIEWER_PATCH_V1" not in s:
    raise SystemExit("Error: run prepare_input_viewer.py BEFORE fix_input_viewer.py")

replacements = [
    (
        '''    if (!sOpen) {
        return 0;
    }
    if (sCapKind != 0) {''',
        '''    if (!sOpen) {
        /* BT3_INPUT_VIEWER_DRAG_FIX_V2: gameplay still gets its mouse events,
         * but forward a copy of mouse movements/clicks to ImGui for dragging.
         * Do not forward keys or pad buttons: those remain gameplay inputs. */
        if (Port_Setting("iv_on", 0) &&
            (ev->type == SDL_EVENT_MOUSE_MOTION || ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN ||
             ev->type == SDL_EVENT_MOUSE_BUTTON_UP)) {
            ImGui_ImplSDL3_ProcessEvent(ev);
        }
        return 0;
    }
    if (sCapKind != 0) {''',
    ),
    (
        '''    if (sPadHold || (sChat && !sOpen)) {
        ImGui::GetIO().ConfigFlags &= ~ImGuiConfigFlags_NavEnableGamepad;''',
        '''    /* No gamepad UI navigation while playing: D-pad/sticks must not move a viewer. */
    if (sPadHold || !sOpen) {
        ImGui::GetIO().ConfigFlags &= ~ImGuiConfigFlags_NavEnableGamepad;''',
    ),
    (
        '''    ImGuiWindowFlags flags=ImGuiWindowFlags_NoResize|ImGuiWindowFlags_NoCollapse|
                           ImGuiWindowFlags_NoScrollbar|ImGuiWindowFlags_NoSavedSettings;''',
        '''    ImGuiWindowFlags flags=ImGuiWindowFlags_NoResize|ImGuiWindowFlags_NoCollapse|
                           ImGuiWindowFlags_NoScrollbar|ImGuiWindowFlags_NoScrollWithMouse|
                           ImGuiWindowFlags_NoNav|ImGuiWindowFlags_NoSavedSettings;''',
    ),
    (
        '''    if (ImGui::Begin(title, NULL, flags)) {
        ImGui::TextDisabled("%s",online && player!=ownSide''',
        '''    if (ImGui::Begin(title, NULL, flags)) {
        ImGui::SetScrollY(0.0f); /* Keep controller art fixed regardless of navigation history. */
        ImGui::TextDisabled("%s",online && player!=ownSide''',
    ),
]
for old, new in replacements:
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"Error: incompatible ui.cpp; expected 1 matching section, found {count}: {old[:82]!r}")
    s = s.replace(old, new, 1)
file.write_text(s, encoding="utf-8", newline="\n")
print("Input Viewer hotfix applied: mouse dragging enabled, pad/keyboard navigation and scrolling disabled")
