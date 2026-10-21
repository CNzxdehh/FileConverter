/* FileConvMenu.c —— 「转换文件格式」的 IExplorerCommand 外壳扩展
 *
 * 作用：让菜单项直接出现在 Windows 11 的**一级右键菜单**（不是"显示更多选项"里）。
 * 纯 C + Win32 COM，不用 C++/STL（本机 MSVC 只装了编译器，没有 C++ 头与 CRT 库；
 * UCRT 的 C 头与库是齐的，所以走 C 路线）。
 *
 * 行为：
 *   父项【转换文件格式】→ EnumSubCommands 返回 N 个子命令（每种转换一个）
 *   子项 Invoke → 启动 FileConverter.exe runm <动词> "文件1" "文件2" ...
 *   （runm 一次性把全部选中文件传进去，多选原生支持）
 *
 * 编译： native\build_native.bat
 */

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <shobjidl.h>
#include <shlwapi.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdio.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "uuid.lib")

/* ---------------- 手动声明 IExplorerCommand ----------------
 * MinGW 的 shobjidl_core.h 里没有这组接口（微软私有扩展），这里按官方 MIDL 定义补齐。
 * 这样本文件在 MSVC / MinGW 下都能编译。
 */
#ifndef __IExplorerCommand_INTERFACE_DEFINED__
#define __IExplorerCommand_INTERFACE_DEFINED__

typedef enum {
    ECS_ENABLED = 0,
    ECS_DISABLED = 0x1,
    ECS_HIDDEN = 0x2,
    ECS_CHECKBOX = 0x4,
    ECS_CHECKED = 0x8,
    ECS_RADIOCHECK = 0x10
} EXPCMDSTATE;

typedef enum {
    ECF_DEFAULT = 0,
    ECF_HASSUBCOMMANDS = 0x1,
    ECF_HASSPLITBUTTON = 0x2,
    ECF_HIDELABEL = 0x4,
    ECF_ISSEPARATOR = 0x8,
    ECF_HASLUASHIELD = 0x10,
    ECF_SEPARATORBEFORE = 0x20,
    ECF_SEPARATORAFTER = 0x40,
    ECF_ISDROPDOWN = 0x80,
    ECF_TOGGLEABLE = 0x100,
    ECF_AUTOMENUICONS = 0x200
} EXPCMDFLAGS;

typedef struct IExplorerCommand IExplorerCommand;
typedef struct IEnumExplorerCommand IEnumExplorerCommand;

typedef struct IExplorerCommandVtbl {
    HRESULT(STDMETHODCALLTYPE *QueryInterface)(IExplorerCommand *This, REFIID riid, void **ppv);
    ULONG(STDMETHODCALLTYPE *AddRef)(IExplorerCommand *This);
    ULONG(STDMETHODCALLTYPE *Release)(IExplorerCommand *This);
    HRESULT(STDMETHODCALLTYPE *GetTitle)(IExplorerCommand *This, IShellItemArray *psia,
                                         LPWSTR *ppszName);
    HRESULT(STDMETHODCALLTYPE *GetIcon)(IExplorerCommand *This, IShellItemArray *psia,
                                        LPWSTR *ppszIcon);
    HRESULT(STDMETHODCALLTYPE *GetToolTip)(IExplorerCommand *This, IShellItemArray *psia,
                                           LPWSTR *ppszInfotip);
    HRESULT(STDMETHODCALLTYPE *GetCanonicalName)(IExplorerCommand *This, GUID *pguid);
    HRESULT(STDMETHODCALLTYPE *GetState)(IExplorerCommand *This, IShellItemArray *psia,
                                         BOOL fOkToBeSlow, EXPCMDSTATE *pCmdState);
    HRESULT(STDMETHODCALLTYPE *Invoke)(IExplorerCommand *This, IShellItemArray *psia,
                                       IBindCtx *pbc);
    HRESULT(STDMETHODCALLTYPE *GetFlags)(IExplorerCommand *This, EXPCMDFLAGS *pFlags);
    HRESULT(STDMETHODCALLTYPE *EnumSubCommands)(IExplorerCommand *This,
                                                IEnumExplorerCommand **ppEnum);
} IExplorerCommandVtbl;

struct IExplorerCommand {
    const IExplorerCommandVtbl *lpVtbl;
};

typedef struct IEnumExplorerCommandVtbl {
    HRESULT(STDMETHODCALLTYPE *QueryInterface)(IEnumExplorerCommand *This, REFIID riid,
                                               void **ppv);
    ULONG(STDMETHODCALLTYPE *AddRef)(IEnumExplorerCommand *This);
    ULONG(STDMETHODCALLTYPE *Release)(IEnumExplorerCommand *This);
    HRESULT(STDMETHODCALLTYPE *Next)(IEnumExplorerCommand *This, ULONG celt,
                                     IExplorerCommand **pUICommand, ULONG *pceltFetched);
    HRESULT(STDMETHODCALLTYPE *Skip)(IEnumExplorerCommand *This, ULONG celt);
    HRESULT(STDMETHODCALLTYPE *Reset)(IEnumExplorerCommand *This);
    HRESULT(STDMETHODCALLTYPE *Clone)(IEnumExplorerCommand *This, IEnumExplorerCommand **ppenum);
} IEnumExplorerCommandVtbl;

struct IEnumExplorerCommand {
    const IEnumExplorerCommandVtbl *lpVtbl;
};

#endif /* __IExplorerCommand_INTERFACE_DEFINED__ */

/* {7B3F9A12-4C6D-4E21-9A3B-112233445566} */
static const GUID CLSID_FileConvMenu = {
    0x7b3f9a12, 0x4c6d, 0x4e21, {0x9a, 0x3b, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66}};

/* 本地定义这些 IID，避免依赖 uuid.lib（本机 SDK 库不全） */
static const GUID IID_IUnknownL = {
    0x00000000, 0x0000, 0x0000, {0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};
static const GUID IID_IClassFactoryL = {
    0x00000001, 0x0000, 0x0000, {0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};
static const GUID IID_IExplorerCommandL = {
    0xa08ce4d0, 0xfa25, 0x44ab, {0xb5, 0x7c, 0xc7, 0xb1, 0xc3, 0x23, 0xe0, 0xb9}};
static const GUID IID_IEnumExplorerCommandL = {
    0xa88826f8, 0x186f, 0x4987, {0xaa, 0xde, 0xea, 0x0c, 0xef, 0x8f, 0xbf, 0xe8}};

#define EQ_IID(a, b) (memcmp((a), (b), sizeof(GUID)) == 0)

static HINSTANCE g_hInst = NULL;

/* ---------------- 转换方案表（gen_verbs.py 从 tasks.py 生成） ---------------- */
typedef struct {
    const wchar_t *id;
    const wchar_t *label;
} VerbDef;

static const VerbDef kVerbs[] = {
#include "verbs_gen.h"
};
static const int kVerbCount = (int)(sizeof(kVerbs) / sizeof(kVerbs[0]));

/* ---------------- 极简字符串缓冲 ---------------- */
typedef struct {
    wchar_t *buf;
    size_t len;
    size_t cap;
} SB;

static int sb_init(SB *sb, size_t cap) {
    sb->buf = (wchar_t *)malloc(cap * sizeof(wchar_t));
    if (!sb->buf) return 0;
    sb->buf[0] = 0;
    sb->len = 0;
    sb->cap = cap;
    return 1;
}

static int sb_need(SB *sb, size_t extra) {
    size_t need = sb->len + extra + 1;
    if (need <= sb->cap) return 1;
    while (sb->cap < need) sb->cap *= 2;
    {
        wchar_t *p = (wchar_t *)realloc(sb->buf, sb->cap * sizeof(wchar_t));
        if (!p) return 0;
        sb->buf = p;
    }
    return 1;
}

static int sb_addn(SB *sb, const wchar_t *s, size_t n) {
    if (!sb_need(sb, n)) return 0;
    memcpy(sb->buf + sb->len, s, n * sizeof(wchar_t));
    sb->len += n;
    sb->buf[sb->len] = 0;
    return 1;
}

static int sb_add(SB *sb, const wchar_t *s) { return sb_addn(sb, s, wcslen(s)); }

static int sb_addc(SB *sb, wchar_t c) { return sb_addn(sb, &c, 1); }

static int sb_addquoted(SB *sb, const wchar_t *s) {
    if (!sb_addc(sb, L'"')) return 0;
    for (; *s; ++s) {
        if (*s == L'"' && !sb_addc(sb, L'\\')) return 0;
        if (!sb_addc(sb, *s)) return 0;
    }
    return sb_addc(sb, L'"');
}

static void sb_free(SB *sb) {
    free(sb->buf);
    sb->buf = NULL;
}

/* ---------------- 路径 ---------------- */
static void GetModuleDir(wchar_t *out, DWORD cch) {
    DWORD n;
    out[0] = 0;
    n = GetModuleFileNameW(g_hInst, out, cch);
    if (n == 0) return;
    while (n > 0 && out[n - 1] != L'\\') --n;
    out[n] = 0;
}

typedef struct {
    wchar_t **items;
    int count;
    int cap;
} PathList;

static void PathsAdd(PathList *pl, const wchar_t *p) {
    size_t len = wcslen(p);
    wchar_t *copy;
    if (pl->count == pl->cap) {
        int nc = pl->cap ? pl->cap * 2 : 8;
        wchar_t **np = (wchar_t **)realloc(pl->items, (size_t)nc * sizeof(wchar_t *));
        if (!np) return;
        pl->items = np;
        pl->cap = nc;
    }
    copy = (wchar_t *)malloc((len + 1) * sizeof(wchar_t));
    if (!copy) return;
    memcpy(copy, p, (len + 1) * sizeof(wchar_t));
    pl->items[pl->count++] = copy;
}

static void PathsFree(PathList *pl) {
    int i;
    for (i = 0; i < pl->count; ++i) free(pl->items[i]);
    free(pl->items);
    pl->items = NULL;
    pl->count = 0;
    pl->cap = 0;
}

static void CollectPaths(IShellItemArray *psia, PathList *pl) {
    DWORD n = 0, i;
    if (!psia) return;
    if (FAILED(psia->lpVtbl->GetCount(psia, &n))) return;
    for (i = 0; i < n; ++i) {
        IShellItem *item = NULL;
        if (SUCCEEDED(psia->lpVtbl->GetItemAt(psia, i, &item)) && item) {
            LPWSTR path = NULL;
            if (SUCCEEDED(item->lpVtbl->GetDisplayName(item, SIGDN_FILESYSPATH, &path)) && path) {
                PathsAdd(pl, path);
                CoTaskMemFree(path);
            }
            item->lpVtbl->Release(item);
        }
    }
}

static HRESULT LaunchVerb(const wchar_t *verb, IShellItemArray *psia) {
    wchar_t dir[MAX_PATH * 2], exe[MAX_PATH * 2];
    SB sb;
    PathList pl = {0};
    int i;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    BOOL ok;

    CollectPaths(psia, &pl);
    if (pl.count == 0) {
        PathsFree(&pl);
        return E_INVALIDARG;
    }

    GetModuleDir(dir, MAX_PATH);
    _snwprintf(exe, MAX_PATH * 2, L"%sFileConverter.exe", dir);

    if (!sb_init(&sb, 512)) {
        PathsFree(&pl);
        return E_OUTOFMEMORY;
    }
    sb_addquoted(&sb, exe);
    sb_add(&sb, L" runm ");
    sb_add(&sb, verb);
    for (i = 0; i < pl.count; ++i) {
        sb_addc(&sb, L' ');
        sb_addquoted(&sb, pl.items[i]);
    }
    PathsFree(&pl);

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    ok = CreateProcessW(NULL, sb.buf, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi);
    sb_free(&sb);
    if (!ok) return HRESULT_FROM_WIN32(GetLastError());
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return S_OK;
}

/* ---------------- 父项 / 子项命令对象 ---------------- */
typedef struct {
    IExplorerCommandVtbl *vtbl;
    LONG ref;
    int verb; /* -1 = 父项 */
} CmdObj;

static const IExplorerCommandVtbl CmdVtbl;

static CmdObj *CmdNew(int verb) {
    CmdObj *o = (CmdObj *)malloc(sizeof(CmdObj));
    if (!o) return NULL;
    o->vtbl = (IExplorerCommandVtbl *)&CmdVtbl;
    o->ref = 1;
    o->verb = verb;
    return o;
}

static HRESULT STDMETHODCALLTYPE Cmd_QueryInterface(IExplorerCommand *This, REFIID riid, void **ppv) {
    CmdObj *o = (CmdObj *)This;
    if (!ppv) return E_POINTER;
    if (EQ_IID(riid, &IID_IUnknownL) || EQ_IID(riid, &IID_IExplorerCommandL)) {
        *ppv = o;
        InterlockedIncrement(&o->ref);
        return S_OK;
    }
    *ppv = NULL;
    return E_NOINTERFACE;
}

static ULONG STDMETHODCALLTYPE Cmd_AddRef(IExplorerCommand *This) {
    return (ULONG)InterlockedIncrement(&((CmdObj *)This)->ref);
}

static ULONG STDMETHODCALLTYPE Cmd_Release(IExplorerCommand *This) {
    CmdObj *o = (CmdObj *)This;
    LONG r = InterlockedDecrement(&o->ref);
    if (r == 0) free(o);
    return (ULONG)r;
}

static HRESULT STDMETHODCALLTYPE Cmd_GetTitle(IExplorerCommand *This, IShellItemArray *psia,
                                              LPWSTR *ppszName) {
    CmdObj *o = (CmdObj *)This;
    const wchar_t *t;
    (void)psia;
    if (!ppszName) return E_POINTER;
    t = (o->verb < 0) ? L"转换文件格式" : kVerbs[o->verb].label;
    *ppszName = (LPWSTR)CoTaskMemAlloc((wcslen(t) + 1) * sizeof(wchar_t));
    if (!*ppszName) return E_OUTOFMEMORY;
    wcscpy(*ppszName, t);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE Cmd_GetIcon(IExplorerCommand *This, IShellItemArray *psia,
                                             LPWSTR *ppszIcon) {
    CmdObj *o = (CmdObj *)This;
    wchar_t dir[MAX_PATH * 2], exe[MAX_PATH * 2];
    (void)psia;
    if (!ppszIcon) return E_POINTER;
    *ppszIcon = NULL;
    if (o->verb >= 0) return S_OK; /* 子项不单独带图标 */
    GetModuleDir(dir, MAX_PATH);
    _snwprintf(exe, MAX_PATH * 2, L"%sFileConverter.exe,0", dir);
    *ppszIcon = (LPWSTR)CoTaskMemAlloc((wcslen(exe) + 1) * sizeof(wchar_t));
    if (!*ppszIcon) return E_OUTOFMEMORY;
    wcscpy(*ppszIcon, exe);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE Cmd_GetToolTip(IExplorerCommand *This, IShellItemArray *psia,
                                                LPWSTR *ppszInfotip) {
    CmdObj *o = (CmdObj *)This;
    const wchar_t *t = L"选中文件后选择要转换成的格式（支持多选）";
    (void)psia;
    if (!ppszInfotip) return E_POINTER;
    *ppszInfotip = NULL;
    if (o->verb >= 0) return S_OK;
    *ppszInfotip = (LPWSTR)CoTaskMemAlloc((wcslen(t) + 1) * sizeof(wchar_t));
    if (!*ppszInfotip) return E_OUTOFMEMORY;
    wcscpy(*ppszInfotip, t);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE Cmd_GetCanonicalName(IExplorerCommand *This, GUID *pguid) {
    (void)This;
    if (!pguid) return E_POINTER;
    memset(pguid, 0, sizeof(GUID));
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE Cmd_GetState(IExplorerCommand *This, IShellItemArray *psia,
                                              BOOL slow, EXPCMDSTATE *pState) {
    (void)This;
    (void)psia;
    (void)slow;
    if (!pState) return E_POINTER;
    *pState = ECS_ENABLED;
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE Cmd_Invoke(IExplorerCommand *This, IShellItemArray *psia,
                                            IBindCtx *pbc) {
    CmdObj *o = (CmdObj *)This;
    HRESULT hrInit;
    HRESULT hr;
    (void)pbc;
    if (o->verb < 0) return S_OK; /* 父项只负责展开子菜单 */
    if (!psia) return S_OK;       /* 没有选中项就直接退出，别往下走 */

    /* ⚠️ 坑：Explorer 的 UI 线程本来就已经初始化过 COM（STA）。
       这时 CoInitializeEx 返回 S_FALSE，**绝不能**再调 CoUninitialize，
       否则会把 Explorer 的 COM 环境拆掉，后续菜单代码直接 fail-fast
       （表现为点菜单项后黑屏，事件日志 KERNELBASE.dll 0xc0000005）。
       只在返回 S_OK（我们真正初始化成功）时才配对 CoUninitialize。 */
    hrInit = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    hr = LaunchVerb(kVerbs[o->verb].id, psia);
    if (hrInit == S_OK) CoUninitialize();
    return hr;
}

static HRESULT STDMETHODCALLTYPE Cmd_GetFlags(IExplorerCommand *This, EXPCMDFLAGS *pFlags) {
    CmdObj *o = (CmdObj *)This;
    if (!pFlags) return E_POINTER;
    *pFlags = (o->verb < 0) ? ECF_HASSUBCOMMANDS : ECF_DEFAULT;
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE Cmd_EnumSubCommands(IExplorerCommand *This,
                                                     IEnumExplorerCommand **ppEnum);

static const IExplorerCommandVtbl CmdVtbl = {
    Cmd_QueryInterface,
    Cmd_AddRef,
    Cmd_Release,
    Cmd_GetTitle,
    Cmd_GetIcon,
    Cmd_GetToolTip,
    Cmd_GetCanonicalName,
    Cmd_GetState,
    Cmd_Invoke,
    Cmd_GetFlags,
    Cmd_EnumSubCommands,
};

/* ---------------- 子命令枚举器 ---------------- */
typedef struct {
    IEnumExplorerCommandVtbl *vtbl;
    LONG ref;
    ULONG pos;
} EnumObj;

static const IEnumExplorerCommandVtbl EnumVtbl;

static HRESULT STDMETHODCALLTYPE Enum_QueryInterface(IEnumExplorerCommand *This, REFIID riid,
                                                     void **ppv) {
    EnumObj *o = (EnumObj *)This;
    if (!ppv) return E_POINTER;
    if (EQ_IID(riid, &IID_IUnknownL) || EQ_IID(riid, &IID_IEnumExplorerCommandL)) {
        *ppv = o;
        InterlockedIncrement(&o->ref);
        return S_OK;
    }
    *ppv = NULL;
    return E_NOINTERFACE;
}

static ULONG STDMETHODCALLTYPE Enum_AddRef(IEnumExplorerCommand *This) {
    return (ULONG)InterlockedIncrement(&((EnumObj *)This)->ref);
}

static ULONG STDMETHODCALLTYPE Enum_Release(IEnumExplorerCommand *This) {
    EnumObj *o = (EnumObj *)This;
    LONG r = InterlockedDecrement(&o->ref);
    if (r == 0) free(o);
    return (ULONG)r;
}

static HRESULT STDMETHODCALLTYPE Enum_Next(IEnumExplorerCommand *This, ULONG celt,
                                           IExplorerCommand **ppCmd, ULONG *pFetched) {
    EnumObj *o = (EnumObj *)This;
    ULONG i = 0;
    ULONG produced;
    if (!ppCmd) return E_POINTER;
    while (i < celt && o->pos < (ULONG)kVerbCount) {
        CmdObj *c = CmdNew((int)o->pos);
        if (!c) break;
        ppCmd[i] = (IExplorerCommand *)c;
        ++o->pos;
        ++i;
    }
    produced = i;                 /* 真正产出的数量（不含后面补的 NULL） */
    while (i < celt) ppCmd[i++] = NULL;
    if (pFetched) *pFetched = produced;
    return (produced == celt) ? S_OK : S_FALSE;
}

static HRESULT STDMETHODCALLTYPE Enum_Skip(IEnumExplorerCommand *This, ULONG celt) {
    EnumObj *o = (EnumObj *)This;
    o->pos += celt;
    return (o->pos <= (ULONG)kVerbCount) ? S_OK : S_FALSE;
}

static HRESULT STDMETHODCALLTYPE Enum_Reset(IEnumExplorerCommand *This) {
    ((EnumObj *)This)->pos = 0;
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE Enum_Clone(IEnumExplorerCommand *This,
                                            IEnumExplorerCommand **ppEnum) {
    EnumObj *o = (EnumObj *)This;
    EnumObj *n;
    if (!ppEnum) return E_POINTER;
    n = (EnumObj *)malloc(sizeof(EnumObj));
    if (!n) return E_OUTOFMEMORY;
    n->vtbl = (IEnumExplorerCommandVtbl *)&EnumVtbl;
    n->ref = 1;
    n->pos = o->pos;
    *ppEnum = (IEnumExplorerCommand *)n;
    return S_OK;
}

static const IEnumExplorerCommandVtbl EnumVtbl = {
    Enum_QueryInterface,
    Enum_AddRef,
    Enum_Release,
    Enum_Next,
    Enum_Skip,
    Enum_Reset,
    Enum_Clone,
};

static HRESULT STDMETHODCALLTYPE Cmd_EnumSubCommands(IExplorerCommand *This,
                                                     IEnumExplorerCommand **ppEnum) {
    CmdObj *o = (CmdObj *)This;
    EnumObj *e;
    if (!ppEnum) return E_POINTER;
    *ppEnum = NULL;
    if (o->verb >= 0) return E_NOTIMPL;
    e = (EnumObj *)malloc(sizeof(EnumObj));
    if (!e) return E_OUTOFMEMORY;
    e->vtbl = (IEnumExplorerCommandVtbl *)&EnumVtbl;
    e->ref = 1;
    e->pos = 0;
    *ppEnum = (IEnumExplorerCommand *)e;
    return S_OK;
}

/* ---------------- 类厂 ---------------- */
typedef struct {
    IClassFactoryVtbl *vtbl;
    LONG ref;
} FactoryObj;

static const IClassFactoryVtbl FactoryVtbl;

static HRESULT STDMETHODCALLTYPE Fact_QueryInterface(IClassFactory *This, REFIID riid, void **ppv) {
    FactoryObj *o = (FactoryObj *)This;
    if (!ppv) return E_POINTER;
    if (EQ_IID(riid, &IID_IUnknownL) || EQ_IID(riid, &IID_IClassFactoryL)) {
        *ppv = o;
        InterlockedIncrement(&o->ref);
        return S_OK;
    }
    *ppv = NULL;
    return E_NOINTERFACE;
}

static ULONG STDMETHODCALLTYPE Fact_AddRef(IClassFactory *This) {
    return (ULONG)InterlockedIncrement(&((FactoryObj *)This)->ref);
}

static ULONG STDMETHODCALLTYPE Fact_Release(IClassFactory *This) {
    FactoryObj *o = (FactoryObj *)This;
    LONG r = InterlockedDecrement(&o->ref);
    if (r == 0) free(o);
    return (ULONG)r;
}

static HRESULT STDMETHODCALLTYPE Fact_CreateInstance(IClassFactory *This, IUnknown *outer,
                                                     REFIID riid, void **ppv) {
    CmdObj *c;
    HRESULT hr;
    (void)This;
    if (!ppv) return E_POINTER;
    *ppv = NULL;
    if (outer) return CLASS_E_NOAGGREGATION;
    c = CmdNew(-1);
    if (!c) return E_OUTOFMEMORY;
    hr = Cmd_QueryInterface((IExplorerCommand *)c, riid, ppv);
    Cmd_Release((IExplorerCommand *)c);
    return hr;
}

static HRESULT STDMETHODCALLTYPE Fact_LockServer(IClassFactory *This, BOOL lock) {
    (void)This;
    (void)lock;
    return S_OK;
}

static const IClassFactoryVtbl FactoryVtbl = {
    Fact_QueryInterface,
    Fact_AddRef,
    Fact_Release,
    Fact_CreateInstance,
    Fact_LockServer,
};

/* ---------------- 导出 ---------------- */
__declspec(dllexport) HRESULT __stdcall DllGetClassObject(REFCLSID rclsid, REFIID riid, void **ppv) {
    FactoryObj *f;
    HRESULT hr;
    if (!EQ_IID(rclsid, &CLSID_FileConvMenu)) return CLASS_E_CLASSNOTAVAILABLE;
    f = (FactoryObj *)malloc(sizeof(FactoryObj));
    if (!f) return E_OUTOFMEMORY;
    f->vtbl = (IClassFactoryVtbl *)&FactoryVtbl;
    f->ref = 1;
    hr = Fact_QueryInterface((IClassFactory *)f, riid, ppv);
    Fact_Release((IClassFactory *)f);
    return hr;
}

__declspec(dllexport) HRESULT __stdcall DllCanUnloadNow(void) {
    return S_FALSE; /* 常驻 explorer，避免反复加载 */
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        g_hInst = (HINSTANCE)hModule;
        DisableThreadLibraryCalls(hModule);
    }
    return TRUE;
}
