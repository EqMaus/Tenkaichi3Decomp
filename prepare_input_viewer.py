#!/usr/bin/env python3
"""Add a locally rendered dual-player PlayStation input viewer to BT3 PC port.
Run AFTER prepare_zcounter_lab.py, BEFORE the release build.
No change to match inputs, counter rules, packets or protocol.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def edit(path, changes):
    f = ROOT / path
    s = f.read_text(encoding='utf-8')
    if 'BT3_INPUT_VIEWER_PATCH_V1' in s:
        print(f'{path}: input viewer already applied')
        return
    for needle, replacement in changes:
        count = s.count(needle)
        if count != 1:
            raise RuntimeError(f'{path}: expected anchor once, found {count}: {needle[:100]!r}')
        s = s.replace(needle, replacement, 1)
    f.write_text(s, encoding='utf-8', newline='\n')
    print(f'{path}: input viewer applied')

viewer_header = r'''/* BT3_INPUT_VIEWER_PATCH_V1: one snapshot per player, independent of the gameplay state. */
typedef struct PortViewerState {
    Uint32 buttons; /* active-high PS2 buttons: Select=1, L3=2, etc. */
    Uint8 rx, ry, lx, ly; /* PS2 pad analogue bytes, 128=neutral */
} PortViewerState;
/* source: 0 = controller, 1 = keyboard; online opponent uses received pad data. */
void PortInput_ViewerGet(int player, int source, int online, int own_side, PortViewerState *out);
void PortInput_ViewerNet(int player, const unsigned char *data);

'''
edit('port/src/gs/ui.h', [
    ('/* ui.cpp */', viewer_header + '/* ui.cpp */'),
])

viewer_input_code = r'''/* BT3_INPUT_VIEWER_PATCH_V1: snapshots of what the game sampled. Render thread only reads copies.
 * The local sources are separate: a pad and a keyboard that share the same game-side port
 * do not falsely illuminate each other's buttons. Online remote input comes from Port_NetInput.
 */
static pthread_mutex_t sViewerMutex = PTHREAD_MUTEX_INITIALIZER;
static PortViewerState sViewerLocal[2][2]; /* [physical local player][pad=0,keyboard=1] */
static PortViewerState sViewerRemote[2];   /* [network game side] */

static void viewer_write(int player, int source, unsigned buttons, unsigned char rx,
                         unsigned char ry, unsigned char lx, unsigned char ly) {
    PortViewerState s;
    if (player < 0 || player >= 2 || source < 0 || source >= 2) { return; }
    s.buttons = buttons;
    s.rx = rx; s.ry = ry; s.lx = lx; s.ly = ly;
    pthread_mutex_lock(&sViewerMutex);
    sViewerLocal[player][source] = s;
    pthread_mutex_unlock(&sViewerMutex);
}

void PortInput_ViewerNet(int player, const unsigned char *data) {
    PortViewerState s;
    if (player < 0 || player >= 2 || data == NULL) { return; }
    s.buttons = (Uint32)(~data[0] & 255) | ((Uint32)(~data[1] & 255) << 8);
    s.rx = data[2]; s.ry = data[3]; s.lx = data[4]; s.ly = data[5];
    pthread_mutex_lock(&sViewerMutex);
    sViewerRemote[player] = s;
    pthread_mutex_unlock(&sViewerMutex);
}

void PortInput_ViewerGet(int player, int source, int online, int own_side, PortViewerState *out) {
    if (out == NULL) { return; }
    memset(out, 0, sizeof(*out));
    out->rx = out->ry = out->lx = out->ly = 128;
    if (player < 0 || player >= 2) { return; }
    if (source < 0 || source > 1) { source = 0; }
    pthread_mutex_lock(&sViewerMutex);
    if (online && player != own_side) {
        *out = sViewerRemote[player];
    } else {
        *out = sViewerLocal[online ? 0 : player][source];
    }
    pthread_mutex_unlock(&sViewerMutex);
}

'''
edit('port/src/gs/gs_input.c', [
    ('int gPortOverlayOpen, gPortInputCapture, gPortChatTyping;',
     'int gPortOverlayOpen, gPortInputCapture, gPortChatTyping;\n\n' + viewer_input_code),
    ('int Port_PadRead(int socket, unsigned char *data) {\n    unsigned btn = 0;',
     '''int Port_PadRead(int socket, unsigned char *data) {
    unsigned btn = 0, pad_buttons = 0, key_buttons = 0;
    unsigned char pad_rx = 128, pad_ry = 128, pad_lx = 128, pad_ly = 128;
    unsigned char key_rx = 128, key_ry = 128, key_lx = 128, key_ly = 128;'''),
    ('                btn |= kActions[a].bit;\n            }\n        }\n        stick_bytes(sDeadzone[socket][0]',
     '                btn |= kActions[a].bit;\n            }\n        }\n        stick_bytes(sDeadzone[socket][0]'), # harmless anchor guard; actual pad button snapshot below
    ('    if (sKeySwallow) {\n        const bool *ks = SDL_GetKeyboardState(NULL);',
     '''    pad_buttons = btn;
    pad_rx = rx; pad_ry = ry; pad_lx = lx; pad_ly = ly;
    if (sKeySwallow) {
        const bool *ks = SDL_GetKeyboardState(NULL);'''),
    ('                btn |= kActions[a].bit;\n            }\n        }\n#define HELD',
     '                btn |= kActions[a].bit;\n                key_buttons |= kActions[a].bit;\n            }\n        }\n#define HELD'),
    ('        if (HELD(16)) { ly = 0x00; }', '        if (HELD(16)) { ly = 0x00; key_ly = 0x00; }'),
    ('        if (HELD(17)) { ly = 0xFF; }', '        if (HELD(17)) { ly = 0xFF; key_ly = 0xFF; }'),
    ('        if (HELD(18)) { lx = 0x00; }', '        if (HELD(18)) { lx = 0x00; key_lx = 0x00; }'),
    ('        if (HELD(19)) { lx = 0xFF; }', '        if (HELD(19)) { lx = 0xFF; key_lx = 0xFF; }'),
    ('        if (HELD(20)) { ry = 0x00; }', '        if (HELD(20)) { ry = 0x00; key_ry = 0x00; }'),
    ('        if (HELD(21)) { ry = 0xFF; }', '        if (HELD(21)) { ry = 0xFF; key_ry = 0xFF; }'),
    ('        if (HELD(22)) { rx = 0x00; }', '        if (HELD(22)) { rx = 0x00; key_rx = 0x00; }'),
    ('        if (HELD(23)) { rx = 0xFF; }', '        if (HELD(23)) { rx = 0xFF; key_rx = 0xFF; }'),
    ('    data[2] = rx; data[3] = ry; data[4] = lx; data[5] = ly;\n    return 18;',
     '''    data[2] = rx; data[3] = ry; data[4] = lx; data[5] = ly;
    viewer_write(socket, 0, pad_buttons, pad_rx, pad_ry, pad_lx, pad_ly);
    viewer_write(socket, 1, key_buttons, key_rx, key_ry, key_lx, key_ly);
    return 18;'''),
])

edit('port/src/gs/net.c', [
    ('extern int Port_PadRead(int socket, unsigned char *data); /* gs_input.c: the keyboard and the controllers */',
     '''extern int Port_PadRead(int socket, unsigned char *data); /* gs_input.c: the keyboard and the controllers */
extern void PortInput_ViewerNet(int player, const unsigned char *data); /* BT3_INPUT_VIEWER_PATCH_V1 */'''),
    ('''    if (sRollMax > 0 && player == !sMe) {
        memcpy(data, sUsed[sTick % RING], PAD); /* their real input, or the guess (roll_tick) */
        return;
    }
    memcpy(data, player >= 0 && player < 2 && sTick < sHave[player] ? sIn[player][sTick % RING] : kIdle, PAD);
}''',
     '''    if (sRollMax > 0 && player == !sMe) {
        memcpy(data, sUsed[sTick % RING], PAD); /* their real input, or the guess (roll_tick) */
        if (!sResim) { PortInput_ViewerNet(player, data); }
        return;
    }
    memcpy(data, player >= 0 && player < 2 && sTick < sHave[player] ? sIn[player][sTick % RING] : kIdle, PAD);
    if (!sResim) { PortInput_ViewerNet(player, data); }
}'''),
])

viewer_ui_code = r'''/* BT3_INPUT_VIEWER_PATCH_V1. PlayStation input viewer; no gameplay or network edits. */
static bool viewer_has(unsigned bits, unsigned bit) { return (bits & bit) != 0; }
static void viewer_box(ImDrawList *d, ImVec2 p, ImVec2 size, const char *label, bool active) {
    ImU32 base = active ? IM_COL32(39, 107, 210, 245) : IM_COL32(42, 49, 68, 230);
    ImU32 edge = active ? IM_COL32(132, 202, 255, 255) : IM_COL32(96, 107, 132, 235);
    d->AddRectFilled(p, ImVec2(p.x + size.x, p.y + size.y), base, 4.0f);
    d->AddRect(p, ImVec2(p.x + size.x, p.y + size.y), edge, 4.0f);
    ImVec2 z = ImGui::CalcTextSize(label);
    d->AddText(ImVec2(p.x + (size.x - z.x)*0.5f, p.y + (size.y - z.y)*0.5f), IM_COL32(250,250,255,255), label);
}
static void viewer_face(ImDrawList *d, ImVec2 c, char kind, bool active) {
    ImU32 color = kind=='T' ? IM_COL32(101,235,173,255) : kind=='C' ? IM_COL32(254,122,132,255) :
                  kind=='S' ? IM_COL32(241,151,226,255) : IM_COL32(126,182,255,255);
    ImU32 dim = active ? color : IM_COL32(119,132,157,245);
    d->AddCircleFilled(c, 17.0f, active ? IM_COL32(62,96,154,245) : IM_COL32(35,44,62,235), 24);
    if (kind == 'T') {
        d->AddTriangle(ImVec2(c.x,c.y-9), ImVec2(c.x-9,c.y+7), ImVec2(c.x+9,c.y+7), dim, 2.4f);
    } else if (kind == 'C') {
        d->AddCircle(c, 8.5f, dim, 24, 2.6f);
    } else if (kind == 'S') {
        d->AddRect(ImVec2(c.x-8,c.y-8), ImVec2(c.x+8,c.y+8), dim, 0, 0, 2.6f);
    } else {
        d->AddLine(ImVec2(c.x-7,c.y-7), ImVec2(c.x+7,c.y+7), dim, 2.8f);
        d->AddLine(ImVec2(c.x-7,c.y+7), ImVec2(c.x+7,c.y-7), dim, 2.8f);
    }
}
static void viewer_joystick(ImDrawList *d, ImVec2 c, unsigned char vx, unsigned char vy, bool pushed, const char *label) {
    ImU32 line = pushed ? IM_COL32(110,195,255,255) : IM_COL32(108,121,150,255);
    float x = ((float)vx-128.0f)/127.0f, y=((float)vy-128.0f)/127.0f;
    if (x < -1) x=-1; if (x>1) x=1;
    if (y < -1) y=-1; if (y>1) y=1;
    d->AddCircleFilled(c, 29.0f, IM_COL32(28,34,49,235), 40);
    d->AddCircle(c, 29.0f, line, 40, 2.0f);
    d->AddLine(ImVec2(c.x-20,c.y), ImVec2(c.x+20,c.y), IM_COL32(70,83,107,180));
    d->AddLine(ImVec2(c.x,c.y-20), ImVec2(c.x,c.y+20), IM_COL32(70,83,107,180));
    ImVec2 tip(c.x+x*19.0f,c.y+y*19.0f);
    d->AddCircleFilled(tip, 9.0f, pushed ? IM_COL32(89,185,255,255) : IM_COL32(177,190,216,255), 24);
    d->AddCircle(tip, 9.0f, IM_COL32(230,237,250,235), 24, 1.3f);
    ImVec2 ts=ImGui::CalcTextSize(label);
    d->AddText(ImVec2(c.x-ts.x*0.5f,c.y+32.0f),IM_COL32(204,214,230,255),label);
}
static void viewer_dpad(ImDrawList *d, ImVec2 c, unsigned b) {
    struct Dir { int x,y; unsigned bit; const char *label; } dirs[] = {
        {0,-1,0x0010,"U"},{0,1,0x0040,"D"},{-1,0,0x0080,"L"},{1,0,0x0020,"R"}};
    for (const Dir &v: dirs) {
        viewer_box(d, ImVec2(c.x + v.x*27-12,c.y + v.y*27-12), ImVec2(24,24),v.label,viewer_has(b,v.bit));
    }
    d->AddRectFilled(ImVec2(c.x-8,c.y-8),ImVec2(c.x+8,c.y+8),IM_COL32(50,59,79,240),2);
}
static void viewer_draw(int player, int source, int online, int ownSide) {
    PortViewerState s;
    PortInput_ViewerGet(player,source,online,ownSide,&s);
    char title[64], kx[24], ky[24];
    snprintf(title,sizeof(title),"Input Viewer - P%d##bt3iv%d",player+1,player);
    snprintf(kx,sizeof(kx),"iv_p%d_x",player+1);
    snprintf(ky,sizeof(ky),"iv_p%d_y",player+1);
    ImGui::SetNextWindowPos(ImVec2((float)Port_Setting(kx, player==0 ? 12 : 377),
                                    (float)Port_Setting(ky, 160)), ImGuiCond_Once);
    ImGui::SetNextWindowSize(ImVec2(350.0f,294.0f),ImGuiCond_Always);
    ImGui::SetNextWindowBgAlpha(0.88f);
    ImGuiWindowFlags flags=ImGuiWindowFlags_NoResize|ImGuiWindowFlags_NoCollapse|
                           ImGuiWindowFlags_NoScrollbar|ImGuiWindowFlags_NoSavedSettings;
    if (ImGui::Begin(title, NULL, flags)) {
        ImGui::TextDisabled("%s",online && player!=ownSide ? "Online opponent (received inputs)" : source==0 ? "Controller" : "Keyboard");
        ImVec2 start=ImGui::GetCursorScreenPos();
        ImDrawList *d=ImGui::GetWindowDrawList();
        auto p=[&](float x,float y){return ImVec2(start.x+x,start.y+y);};
        unsigned b=s.buttons;
        viewer_box(d,p(5,3), ImVec2(67,25),"L2",viewer_has(b,0x0100));
        viewer_box(d,p(79,3),ImVec2(67,25),"L1",viewer_has(b,0x0400));
        viewer_box(d,p(184,3),ImVec2(67,25),"R1",viewer_has(b,0x0800));
        viewer_box(d,p(258,3),ImVec2(67,25),"R2",viewer_has(b,0x0200));
        viewer_box(d,p(101,39),ImVec2(61,23),"Select",viewer_has(b,0x0001));
        viewer_box(d,p(168,39),ImVec2(61,23),"Start",viewer_has(b,0x0008));
        viewer_dpad(d,p(68,119),b);
        viewer_face(d,p(273,86),'T',viewer_has(b,0x1000));
        viewer_face(d,p(306,119),'C',viewer_has(b,0x2000));
        viewer_face(d,p(240,119),'S',viewer_has(b,0x8000));
        viewer_face(d,p(273,152),'X',viewer_has(b,0x4000));
        viewer_joystick(d,p(123,187),s.lx,s.ly,viewer_has(b,0x0002),"L3");
        viewer_joystick(d,p(203,187),s.rx,s.ry,viewer_has(b,0x0004),"R3");
        ImGui::Dummy(ImVec2(330,235));
    }
    ImVec2 at=ImGui::GetWindowPos();
    if (ImGui::IsMouseReleased(ImGuiMouseButton_Left)) {
        int x=(int)(at.x+0.5f),y=(int)(at.y+0.5f);
        if (x!=Port_Setting(kx,player==0?12:377) || y!=Port_Setting(ky,160)) {
            Port_SettingSave(kx,x); Port_SettingSave(ky,y); Port_SettingsWrite();
        }
    }
    ImGui::End();
}
static void viewer_options(void) {
    bool enabled = Port_Setting("iv_on",0)!=0;
    if (ImGui::Checkbox("Input Viewer",&enabled)) {
        Port_SettingSave("iv_on",enabled?1:0);
        Port_SettingsWrite();
    }
    ImGui::SetItemTooltip("Show PlayStation controls and live analogue stick positions over the game. Drag a viewer's title to move it.");
    if (enabled) {
        ImGui::Indent();
        const char *sources[]={"Controller","Keyboard"};
        for (int p=0;p<2;p++) {
            char kshow[24],ksrc[24],lbl[64];
            snprintf(kshow,sizeof(kshow),"iv_p%d",p+1);
            snprintf(ksrc,sizeof(ksrc),"iv_src_p%d",p+1);
            bool show=Port_Setting(kshow,p==0?1:0)!=0;
            snprintf(lbl,sizeof(lbl),"Player %d##inputviewer_p%d",p+1,p);
            if (ImGui::Checkbox(lbl,&show)) { Port_SettingSave(kshow,show?1:0); Port_SettingsWrite(); }
            if (show) {
                int src=Port_Setting(ksrc,0);
                if (src<0 || src>1) src=0;
                ImGui::SameLine(); ImGui::SetNextItemWidth(160.0f);
                snprintf(lbl,sizeof(lbl),"##inputviewer_source_p%d",p+1);
                if (ImGui::Combo(lbl,&src,sources,2)) { Port_SettingSave(ksrc,src); Port_SettingsWrite(); }
            }
        }
        ImGui::TextDisabled("In online play, opponents' received inputs are shown regardless of their device.");
        ImGui::TextDisabled("Drag each viewer by its title bar to choose its position.");
        ImGui::Unindent();
    }
    ImGui::Separator();
}

'''
edit('port/src/gs/ui.cpp', [
    ('static void ui_tab(PortVideo &v) {', viewer_ui_code + 'static void ui_tab(PortVideo &v) {\n    viewer_options();'),
    ('    bool meter = sReady && meter_on();',
     '    bool meter = sReady && meter_on();\n    bool iv = sReady && Port_Setting("iv_on",0)!=0 && !sOpen && !sQuit;'),
    ('!sOpen && !sQuit && !notice && !overlay && !meter && !names && !bars && !chat',
     '!sOpen && !sQuit && !notice && !overlay && !meter && !names && !bars && !chat && !iv'),
    ('    if (meter) {\n        meter_draw();\n    }',
     '''    if (meter) {
        meter_draw();
    }
    if (iv) {
        int online = Port_NetActive();
        int ownSide = online ? Port_NetMe() : 0;
        for (int player=0; player<2; player++) {
            char key[24];
            snprintf(key,sizeof(key),"iv_p%d",player+1);
            if (Port_Setting(key,player==0?1:0)) {
                snprintf(key,sizeof(key),"iv_src_p%d",player+1);
                viewer_draw(player,Port_Setting(key,0),online,ownSide);
            }
        }
    }'''),
])
print('BT3 input viewer patch applied to 4 source files. Build using your existing GitHub Actions workflow.')
