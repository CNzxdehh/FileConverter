/* FileConvCtx.c —— 经典 IContextMenu 外壳扩展（真正的级联子菜单）
 *
 * 为什么用它：注册表级联（SubCommands / 父键下挂 shell 子键）在这台 Win11 上
 * 渲染不出来，而 Bandizip / 7-Zip 那种"shell 扩展自己 InsertMenu 一个 popup"
 * 的方式稳定可用。所以实现 IContextMenu：
 *
 *   QueryContextMenu → CreatePopupMenu() 填 17 项 → InsertMenu 到右键菜单
 *   InvokeCommand   → 启动 FileConverter.exe runm <动词> "文件1" "文件2"...
 *
 * 注册：HKCU\Software\Classes\{*|Directory}\shellex\ContextMenuHandlers\FileConv
 *       = {B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}
 *
 * 注意：IShellExtInit 与 IContextMenu 的方法都在第 4 槽（冲突），
 * 所以必须用「双 vtable 子对象」布局，QueryInterface 返回不同的子对象地址。
 */

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <shobjidl.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdio.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "shlwapi.lib")

/* {B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D} */
static const GUID CLSID_FileConvCtx = {
    0xb2c4e111, 0x7a9d, 0x4c3e, {0x8f, 0x21, 0x9d, 0x4e, 0x5a, 0x6b, 0x7c, 0x8d}};

static const GUID IID_IUnknownL = {
    0x00000000, 0x0000, 0x0000, {0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};
static const GUID IID_IClassFactoryL = {
    0x00000001, 0x0000, 0x0000, {0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};
static const GUID IID_IShellExtInitL = {
    0x000214e8, 0x0000, 0x0000, {0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};
static const GUID IID_IContextMenuL = {
    0x000214e4, 0x0000, 0x0000, {0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46}};

#define EQ_GUID(a, b) (memcmp((a), (b), sizeof(GUID)) == 0)

static HINSTANCE g_hInst = NULL;

/* ---- 转换方案表（gen_verbs.py 生成） ---- */
typedef struct {
    const wchar_t *id;
    const wchar_t *label;
} VerbDef;

static const VerbDef kVerbs[] = {
#include "verbs_gen.h"
};
static const int kVerbCount = (int)(sizeof(kVerbs) / sizeof(kVerbs[0]));

/* ---- 调试日志（排查"点了没反应"用，确认完就关掉 FCCTX_DEBUG） ---- */
#ifndef FCCTX_DEBUG
#define FCCTX_DEBUG 1
#endif
#if FCCTX_DEBUG
#define FCCTX_LOG L"C:\\mgtmp\\fileconv_ctx.log"
static void DbgLog(const wchar_t *fmt, ...) {
    FILE *f;
    va_list ap;
    f = _wfopen(FCCTX_LOG, L"a, ccs=UTF-8");
    if (!f) return;
    va_start(ap, fmt);
    vfwprintf(f, fmt, ap);
    va_end(ap);
    fputwc(L'\n', f);
    fclose(f);
}
#else
static void DbgLog(const wchar_t *fmt, ...) { (void)fmt; }
#endif

/* ---- 路径表 ---- */
typedef struct {
    wchar_t **items;
    int count;
    int cap;
} PathList;

static void PathsAdd(PathList *pl, const wchar_t *p) {
    size_t len;
    wchar_t *copy;
    if (!p || !*p) return;
    if (pl->count == pl->cap) {
        int nc = pl->cap ? pl->cap * 2 : 16;
        wchar_t **np = (wchar_t **)realloc(pl->items, (size_t)nc * sizeof(wchar_t *));
        if (!np) return;
        pl->items = np;
        pl->cap = nc;
    }
    len = wcslen(p);
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

static void CollectFromDataObject(IDataObject *pdtobj, PathList *pl) {
    FORMATETC fmt;
    STGMEDIUM stg;

    if (!pdtobj) return;
    memset(&fmt, 0, sizeof(fmt));
    fmt.cfFormat = CF_HDROP;
    fmt.dwAspect = DVASPECT_CONTENT;
    fmt.lindex = -1;                    /* 必须给 -1，否则部分数据源 GetData 失败 */
    fmt.tymed = TYMED_HGLOBAL;
    memset(&stg, 0, sizeof(stg));

    if (FAILED(pdtobj->lpVtbl->GetData(pdtobj, &fmt, &stg))) return;
    if (stg.tymed == TYMED_HGLOBAL && stg.hGlobal) {
        HDROP hdrop = (HDROP)GlobalLock(stg.hGlobal);
        if (hdrop) {
            UINT n = DragQueryFileW(hdrop, 0xFFFFFFFF, NULL, 0);
            UINT i;
            for (i = 0; i < n; ++i) {
                UINT need = DragQueryFileW(hdrop, i, NULL, 0);
                wchar_t *buf;
                if (need == 0) continue;
                buf = (wchar_t *)malloc((need + 1) * sizeof(wchar_t));
                if (!buf) continue;
                DragQueryFileW(hdrop, i, buf, need + 1);
                PathsAdd(pl, buf);
                free(buf);
            }
            GlobalUnlock(stg.hGlobal);
        }
    }
    ReleaseStgMedium(&stg);
}

static void Launch(const wchar_t *verb, PathList *pl) {
    wchar_t dir[MAX_PATH * 2], exe[MAX_PATH * 2];
    size_t cap = 1024, len = 0;
    wchar_t *cmd;
    int i;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;

    if (pl->count == 0) return;

    GetModuleFileNameW(g_hInst, dir, MAX_PATH);
    {
        wchar_t *p = wcsrchr(dir, L'\\');
        if (p) *(p + 1) = 0;
    }
    _snwprintf(exe, MAX_PATH * 2, L"%sFileConverter.exe", dir);
    exe[MAX_PATH * 2 - 1] = 0;
    if (GetFileAttributesW(exe) == INVALID_FILE_ATTRIBUTES) return;  /* exe 不在，别乱启动 */

    for (i = 0; i < pl->count; ++i) cap += wcslen(pl->items[i]) + 4;
    cmd = (wchar_t *)malloc(cap * sizeof(wchar_t));
    if (!cmd) return;
    cmd[0] = 0;
    {
        /* _snwprintf 被截断时返回 -1，直接累加会把 len 减回负数 → 越界写，必须兜住 */
        int w = _snwprintf(cmd + len, cap - len, L"\"%s\" runm %s", exe, verb);
        if (w < 0 || (size_t)w >= cap - len) { free(cmd); return; }
        len += (size_t)w;
    }
    for (i = 0; i < pl->count; ++i) {
        int w = _snwprintf(cmd + len, cap - len, L" \"%s\"", pl->items[i]);
        if (w < 0 || (size_t)w >= cap - len) break;
        len += (size_t)w;
    }

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
    free(cmd);
}

/* ---- 对象：双 vtable 子对象 ---- */
typedef struct _CtxObj {
    const IContextMenuVtbl *lpCtx;      /* offset 0  —— IContextMenu 从这里开始 */
    const IShellExtInitVtbl *lpShl;     /* offset 8  —— IShellExtInit 从这里开始 */
    LONG ref;
    PathList paths;
    UINT idCmdFirst;                    /* QueryContextMenu 拿到的起始 ID */
    BOOL menu_built;                    /* 是否真的插过菜单（决定怎么解释 Invoke 的 ID） */
} CtxObj;

#define FROM_CTX(p) ((CtxObj *)(p))
#define FROM_SHL(p) ((CtxObj *)((BYTE *)(p) - offsetof(CtxObj, lpShl)))

static HRESULT STDMETHODCALLTYPE Shl_QueryInterface(IShellExtInit *This, REFIID riid, void **ppv);
static ULONG STDMETHODCALLTYPE Shl_AddRef(IShellExtInit *This);
static ULONG STDMETHODCALLTYPE Shl_Release(IShellExtInit *This);
static HRESULT STDMETHODCALLTYPE Shl_Initialize(IShellExtInit *This, PCIDLIST_ABSOLUTE,
                                                IDataObject *, HKEY);

static HRESULT STDMETHODCALLTYPE Ctx_QueryInterface(IContextMenu *This, REFIID riid, void **ppv);
static ULONG STDMETHODCALLTYPE Ctx_AddRef(IContextMenu *This);
static ULONG STDMETHODCALLTYPE Ctx_Release(IContextMenu *This);
static HRESULT STDMETHODCALLTYPE Ctx_QueryContextMenu(IContextMenu *This, HMENU, UINT, UINT,
                                                      UINT, UINT);
static HRESULT STDMETHODCALLTYPE Ctx_InvokeCommand(IContextMenu *This, CMINVOKECOMMANDINFO *);
static HRESULT STDMETHODCALLTYPE Ctx_GetCommandString(IContextMenu *This, UINT_PTR, UINT,
                                                      UINT *, LPSTR, UINT);

static const IContextMenuVtbl CtxVtbl = {
    Ctx_QueryInterface, Ctx_AddRef, Ctx_Release,
    Ctx_QueryContextMenu, Ctx_InvokeCommand, Ctx_GetCommandString,
};

static const IShellExtInitVtbl ShlVtbl = {
    Shl_QueryInterface, Shl_AddRef, Shl_Release, Shl_Initialize,
};

static HRESULT QueryInterfaceCommon(CtxObj *o, REFIID riid, void **ppv) {
    if (!ppv) return E_POINTER;
    if (EQ_GUID(riid, &IID_IUnknownL) || EQ_GUID(riid, &IID_IContextMenuL)) {
        *ppv = &o->lpCtx;                       /* 指向 offset 0 的子对象 */
        InterlockedIncrement(&o->ref);
        return S_OK;
    }
    if (EQ_GUID(riid, &IID_IShellExtInitL)) {
        *ppv = &o->lpShl;                       /* 指向 offset 8 的子对象 */
        InterlockedIncrement(&o->ref);
        return S_OK;
    }
    *ppv = NULL;
    return E_NOINTERFACE;
}

static HRESULT STDMETHODCALLTYPE Ctx_QueryInterface(IContextMenu *This, REFIID riid, void **ppv) {
    return QueryInterfaceCommon(FROM_CTX(This), riid, ppv);
}
static ULONG STDMETHODCALLTYPE Ctx_AddRef(IContextMenu *This) {
    return (ULONG)InterlockedIncrement(&FROM_CTX(This)->ref);
}
static ULONG STDMETHODCALLTYPE Ctx_Release(IContextMenu *This) {
    CtxObj *o = FROM_CTX(This);
    LONG r = InterlockedDecrement(&o->ref);
    if (r == 0) {
        PathsFree(&o->paths);
        free(o);
    }
    return (ULONG)r;
}

static HRESULT STDMETHODCALLTYPE Shl_QueryInterface(IShellExtInit *This, REFIID riid, void **ppv) {
    return QueryInterfaceCommon(FROM_SHL(This), riid, ppv);
}
static ULONG STDMETHODCALLTYPE Shl_AddRef(IShellExtInit *This) {
    return (ULONG)InterlockedIncrement(&FROM_SHL(This)->ref);
}
static ULONG STDMETHODCALLTYPE Shl_Release(IShellExtInit *This) {
    CtxObj *o = FROM_SHL(This);
    LONG r = InterlockedDecrement(&o->ref);
    if (r == 0) {
        PathsFree(&o->paths);
        free(o);
    }
    return (ULONG)r;
}

static HRESULT STDMETHODCALLTYPE Shl_Initialize(IShellExtInit *This, PCIDLIST_ABSOLUTE pidl,
                                                IDataObject *pdtobj, HKEY hkeyProgID) {
    CtxObj *o = FROM_SHL(This);
    (void)pidl;
    (void)hkeyProgID;
    PathsFree(&o->paths);
    CollectFromDataObject(pdtobj, &o->paths);
    return o->paths.count > 0 ? S_OK : E_FAIL;
}

static HRESULT STDMETHODCALLTYPE Ctx_QueryContextMenu(IContextMenu *This, HMENU hmenu,
                                                      UINT indexMenu, UINT idCmdFirst,
                                                      UINT idCmdLast, UINT uFlags) {
    CtxObj *o = FROM_CTX(This);
    HMENU sub;
    int i;

    (void)idCmdLast;
    if (uFlags & CMF_DEFAULTONLY) return MAKE_HRESULT(SEVERITY_SUCCESS, 0, 0);
    if (o->paths.count == 0) return MAKE_HRESULT(SEVERITY_SUCCESS, 0, 0);

    sub = CreatePopupMenu();
    if (!sub) return MAKE_HRESULT(SEVERITY_SUCCESS, 0, 0);

    for (i = 0; i < kVerbCount; ++i) {
        AppendMenuW(sub, MF_STRING, (UINT_PTR)(idCmdFirst + (UINT)i), kVerbs[i].label);
    }

    InsertMenuW(hmenu, indexMenu, MF_BYPOSITION | MF_POPUP | MF_STRING,
                (UINT_PTR)sub, L"转换文件格式");

    o->idCmdFirst = idCmdFirst;
    o->menu_built = TRUE;
    DbgLog(L"QueryContextMenu: idCmdFirst=%u 路径数=%d 插入位置=%u",
           idCmdFirst, o->paths.count, indexMenu);
    return MAKE_HRESULT(SEVERITY_SUCCESS, 0, (UINT)kVerbCount);
}

static HRESULT STDMETHODCALLTYPE Ctx_InvokeCommand(IContextMenu *This,
                                                   CMINVOKECOMMANDINFO *pici) {
    CtxObj *o = FROM_CTX(This);
    UINT raw;
    int idx = -1;

    if (!pici) return E_INVALIDARG;
    DbgLog(L"InvokeCommand: lpVerb=0x%IX hi=%u lo=%u cbSize=%u idCmdFirst=%u",
           (UINT_PTR)pici->lpVerb, HIWORD((UINT_PTR)pici->lpVerb),
           LOWORD((UINT_PTR)pici->lpVerb), pici->cbSize, o->idCmdFirst);
    if (HIWORD((UINT_PTR)pici->lpVerb) != 0) return E_INVALIDARG;   /* 字符串动词不支持 */

    /* ⚠️ 关键防坑：shell 传进来的低 16 位到底是「绝对菜单 ID」还是「相对 idCmdFirst
     *   的偏移」，不同宿主实现不一致（自己写的宿主通常传偏移，Explorer 实际传绝对 ID）。
     *   搞反了的表现就是"点了没反应"。这里两种解释都接受，彻底消掉这个风险。 */
    raw = LOWORD((UINT_PTR)pici->lpVerb);
    if (o->menu_built && raw >= o->idCmdFirst
        && raw < o->idCmdFirst + (UINT)kVerbCount) {
        idx = (int)(raw - o->idCmdFirst);          /* 绝对 ID */
        DbgLog(L"  → 按绝对 ID 解释：idx=%d", idx);
    } else if (raw < (UINT)kVerbCount) {
        idx = (int)raw;                            /* 相对偏移 */
        DbgLog(L"  → 按相对偏移解释：idx=%d", idx);
    }
    if (idx < 0 || idx >= kVerbCount) {
        DbgLog(L"  → 无法识别的 ID，放弃（raw=%u idCmdFirst=%u 项数=%d）",
               raw, o->idCmdFirst, kVerbCount);
        return E_INVALIDARG;
    }

    DbgLog(L"  → 触发第 %d 项：%s（共 %d 个文件）", idx, kVerbs[idx].id, o->paths.count);
    Launch(kVerbs[idx].id, &o->paths);
    return S_OK;
}

/* 经典菜单会用它在状态栏显示提示，A/W 两个版本都得给，否则菜单项会变灰或没提示 */
static HRESULT STDMETHODCALLTYPE Ctx_GetCommandString(IContextMenu *This, UINT_PTR idCmd,
                                                      UINT uType, UINT *pwReserved,
                                                      LPSTR pszName, UINT cchMax) {
    (void)This;
    (void)pwReserved;
    if (!pszName || cchMax == 0) return E_INVALIDARG;
    if (idCmd >= (UINT_PTR)kVerbCount) return E_INVALIDARG;
    pszName[0] = 0;

    /* 校验：只回答"这个 id 合法吗"，不写内容 */
    if (uType == GCS_VALIDATEA || uType == GCS_VALIDATEW) return S_OK;

    if (uType == GCS_VERBA || uType == GCS_VERBW) {
        if (uType == GCS_VERBA) {
            WideCharToMultiByte(CP_ACP, 0, kVerbs[idCmd].id, -1, pszName, (int)cchMax, NULL, NULL);
        } else {
            wchar_t *w = (wchar_t *)pszName;
            wcsncpy(w, kVerbs[idCmd].id, cchMax - 1);
            w[cchMax - 1] = 0;
        }
        return S_OK;
    }

    if (uType == GCS_HELPTEXTA || uType == GCS_HELPTEXTW) {
        wchar_t tmp[256];
        _snwprintf(tmp, 256, L"用 FileConverter 执行：%s", kVerbs[idCmd].label);
        tmp[255] = 0;
        if (uType == GCS_HELPTEXTA) {
            WideCharToMultiByte(CP_ACP, 0, tmp, -1, pszName, (int)cchMax, NULL, NULL);
        } else {
            wchar_t *w = (wchar_t *)pszName;
            wcsncpy(w, tmp, cchMax - 1);
            w[cchMax - 1] = 0;
        }
        return S_OK;
    }
    return E_NOTIMPL;
}

/* ---- 类厂 ---- */
typedef struct {
    IClassFactoryVtbl *lpVtbl;
    LONG ref;
} FactoryObj;

static HRESULT STDMETHODCALLTYPE Fact_QueryInterface(IClassFactory *This, REFIID riid, void **ppv) {
    FactoryObj *o = (FactoryObj *)This;
    if (!ppv) return E_POINTER;
    if (EQ_GUID(riid, &IID_IUnknownL) || EQ_GUID(riid, &IID_IClassFactoryL)) {
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
    CtxObj *c;
    HRESULT hr;
    (void)This;
    if (!ppv) return E_POINTER;
    *ppv = NULL;
    if (outer) return CLASS_E_NOAGGREGATION;
    c = (CtxObj *)malloc(sizeof(CtxObj));
    if (!c) return E_OUTOFMEMORY;
    c->lpCtx = &CtxVtbl;
    c->lpShl = &ShlVtbl;
    c->ref = 1;
    c->paths.items = NULL;
    c->paths.count = 0;
    c->paths.cap = 0;
    c->idCmdFirst = 0;
    c->menu_built = FALSE;

    hr = QueryInterfaceCommon(c, riid, ppv);
    Ctx_Release((IContextMenu *)&c->lpCtx);
    return hr;
}
static HRESULT STDMETHODCALLTYPE Fact_LockServer(IClassFactory *This, BOOL lock) {
    (void)This;
    (void)lock;
    return S_OK;
}

static const IClassFactoryVtbl FactVtbl = {
    Fact_QueryInterface, Fact_AddRef, Fact_Release, Fact_CreateInstance, Fact_LockServer,
};

__declspec(dllexport) HRESULT __stdcall DllGetClassObject(REFCLSID rclsid, REFIID riid, void **ppv) {
    FactoryObj *f;
    HRESULT hr;
    if (!EQ_GUID(rclsid, &CLSID_FileConvCtx)) return CLASS_E_CLASSNOTAVAILABLE;
    f = (FactoryObj *)malloc(sizeof(FactoryObj));
    if (!f) return E_OUTOFMEMORY;
    f->lpVtbl = (IClassFactoryVtbl *)&FactVtbl;
    f->ref = 1;
    hr = Fact_QueryInterface((IClassFactory *)f, riid, ppv);
    Fact_Release((IClassFactory *)f);
    return hr;
}

__declspec(dllexport) HRESULT __stdcall DllCanUnloadNow(void) { return S_FALSE; }

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        g_hInst = (HINSTANCE)hModule;
        DisableThreadLibraryCalls(hModule);
    }
    return TRUE;
}
