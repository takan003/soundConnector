"""
SoundConnector — GUI 應用程式 (tkinter)
直接執行此檔案即可開啟視窗介面。
"""
import ctypes
import ctypes.wintypes as _wt
import json
import os
import pathlib
import socket
import sys
import threading
import tkinter as tk
import webbrowser

try:
    from PIL import Image as _PILImage, ImageTk as _PILImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

_ICON_FILE = pathlib.Path(__file__).resolve().parent / "soundConnector.ico"
from datetime import datetime


# ──────────────────────────────────────────────────────────────────────────────
# Windows 系統匣原生實作（純 ctypes，不依賴 pystray）
# ──────────────────────────────────────────────────────────────────────────────

class _WinTrayIcon:
    """使用純 Win32 API 在系統匣常駐的圖示。

    在獨立的背景執行緒中跑訊息迴圈；透過 on_show / on_quit 回呼與主程式溝通。
    """
    _WM_TRAY      = 0x0401          # 自訂回呼訊息
    _WM_STOP      = 0x0402          # 停止訊息
    _NIM_ADD      = 0
    _NIM_MODIFY   = 1
    _NIM_DELETE   = 2
    _NIF_MESSAGE  = 0x01
    _NIF_ICON     = 0x02
    _NIF_TIP      = 0x04
    _WM_RBUTTONUP = 0x0205
    _WM_LBUTTONDBLCLK = 0x0203
    _WS_POPUP     = 0x80000000
    _WM_COMMAND   = 0x0111
    _MF_STRING    = 0x00000000
    _MF_SEPARATOR = 0x00000800
    _TPM_NONOTIFY = 0x0080
    _TPM_RETURNCMD = 0x0100
    _IMAGE_ICON   = 1
    _LR_LOADFROMFILE = 0x0010
    _LR_DEFAULTSIZE  = 0x0040

    def __init__(self, ico_path: pathlib.Path, tooltip: str,
                 label_show: str, label_quit: str,
                 on_show, on_quit):
        self._ico_path  = str(ico_path)
        self._tooltip   = tooltip
        self._label_show = label_show
        self._label_quit = label_quit
        self._on_show   = on_show
        self._on_quit   = on_quit
        self._hwnd      = None
        self._hicon     = None
        self._thread    = None
        self._ready     = threading.Event()

    # ── 公開方法 ──────────────────────────────────────────────────────────────

    def start(self):
        """在背景執行緒中啟動系統匣圖示。"""
        self._thread = threading.Thread(target=self._run, daemon=False)
        self._thread.start()
        self._ready.wait(timeout=5.0)   # 等待視窗建立完成

    def stop(self):
        if self._hwnd:
            ctypes.windll.user32.PostMessageW(self._hwnd, self._WM_STOP, 0, 0)

    # ── 內部訊息迴圈 ─────────────────────────────────────────────────────────

    def _run(self):
        import ctypes, ctypes.wintypes as wt

        user32  = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32

        # 定義 WNDPROC 型別（64-bit: WPARAM/LPARAM 須用 64-bit 型別）
        WNDPROCTYPE = ctypes.WINFUNCTYPE(
            ctypes.c_longlong,    # LRESULT
            ctypes.c_void_p,      # HWND
            ctypes.c_uint,        # UINT msg
            ctypes.c_ulonglong,   # WPARAM (64-bit)
            ctypes.c_longlong,    # LPARAM (64-bit)
        )

        _self_ref = self     # 避免 lambda 閉包在 GC 後失效

        @WNDPROCTYPE
        def wndproc(hwnd, msg, wparam, lparam):
            return _self_ref._wndproc(hwnd, msg, wparam, lparam)

        self._wndproc_ref = wndproc   # 防 GC

        class WNDCLASSEX(ctypes.Structure):
            _fields_ = [
                ('cbSize',        wt.UINT),
                ('style',         wt.UINT),
                ('lpfnWndProc',   WNDPROCTYPE),
                ('cbClsExtra',    ctypes.c_int),
                ('cbWndExtra',    ctypes.c_int),
                ('hInstance',     wt.HMODULE),
                ('hIcon',         wt.HICON),
                ('hCursor',       ctypes.c_void_p),
                ('hbrBackground', ctypes.c_void_p),
                ('lpszMenuName',  wt.LPCWSTR),
                ('lpszClassName', wt.LPCWSTR),
                ('hIconSm',       wt.HICON),
            ]

        cls_name = f"SC_Tray_{id(self)}"
        hmod = kernel32.GetModuleHandleW(None)

        wc = WNDCLASSEX()
        wc.cbSize = ctypes.sizeof(WNDCLASSEX)
        wc.lpfnWndProc = wndproc
        wc.hInstance   = hmod
        wc.lpszClassName = cls_name

        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            self._ready.set()
            return

        hwnd = user32.CreateWindowExW(
            0, cls_name, "SC_Tray",
            self._WS_POPUP, 0, 0, 0, 0, 0, None, hmod, None)
        if not hwnd:
            user32.UnregisterClassW(cls_name, hmod)
            self._ready.set()
            return
        self._hwnd = hwnd

        # 載入圖示
        self._hicon = user32.LoadImageW(
            None, self._ico_path, self._IMAGE_ICON,
            32, 32, self._LR_LOADFROMFILE)

        # 加入通知區域
        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [
                ('cbSize',           wt.DWORD),
                ('hWnd',             wt.HWND),
                ('uID',              wt.UINT),
                ('uFlags',           wt.UINT),
                ('uCallbackMessage', wt.UINT),
                ('hIcon',            wt.HICON),
                ('szTip',            ctypes.c_wchar * 128),
            ]
        self._NOTIFYICONDATA = NOTIFYICONDATA  # 供後續使用

        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd   = hwnd
        nid.uID    = 1
        nid.uFlags = self._NIF_MESSAGE | self._NIF_ICON | self._NIF_TIP
        nid.uCallbackMessage = self._WM_TRAY
        nid.hIcon  = self._hicon or 0
        nid.szTip  = self._tooltip[:127]
        shell32.Shell_NotifyIconW(self._NIM_ADD, ctypes.byref(nid))
        self._nid_buf = nid   # 防 GC

        self._ready.set()     # 通知 start() 已完成

        # 訊息迴圈
        msg = wt.MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # 清理
        shell32.Shell_NotifyIconW(self._NIM_DELETE, ctypes.byref(nid))
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(cls_name, hmod)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        WM_DESTROY = 2
        if msg == self._WM_STOP:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        if msg == WM_DESTROY:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        if msg == self._WM_TRAY:
            lo = lparam & 0xFFFF
            if lo == self._WM_RBUTTONUP:
                self._show_menu(hwnd)
                return 0
            if lo == self._WM_LBUTTONDBLCLK:
                if self._on_show:
                    self._on_show()
                return 0
        _def = ctypes.windll.user32.DefWindowProcW
        _def.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                         ctypes.c_ulonglong, ctypes.c_longlong]
        _def.restype  = ctypes.c_longlong
        return _def(hwnd, msg, wparam, lparam)

    def _show_menu(self, hwnd):
        import pathlib as _pl
        _pl.Path(__file__).parent.joinpath("tray_debug.txt").write_text(
            f"show={self._label_show!r}  quit={self._label_quit!r}", encoding="utf-8")

        user32 = ctypes.windll.user32

        # ── 設定所有 API 的正確型別 ─────────────────────────────────────────
        user32.CreatePopupMenu.argtypes  = []
        user32.CreatePopupMenu.restype   = ctypes.c_void_p
        user32.InsertMenuItemW.argtypes  = [ctypes.c_void_p, ctypes.c_uint,
                                            ctypes.c_bool, ctypes.c_void_p]
        user32.InsertMenuItemW.restype   = ctypes.c_bool
        user32.TrackPopupMenu.argtypes   = [ctypes.c_void_p, ctypes.c_uint,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_void_p, ctypes.c_void_p]
        user32.TrackPopupMenu.restype    = ctypes.c_int
        user32.DestroyMenu.argtypes      = [ctypes.c_void_p]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]

        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return

        # ── MENUITEMINFOW 結構（64-bit Windows，sizeof = 80）─────────────────
        class MENUITEMINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize",        ctypes.c_uint),
                ("fMask",         ctypes.c_uint),
                ("fType",         ctypes.c_uint),
                ("fState",        ctypes.c_uint),
                ("wID",           ctypes.c_uint),
                ("hSubMenu",      ctypes.c_void_p),
                ("hbmpChecked",   ctypes.c_void_p),
                ("hbmpUnchecked", ctypes.c_void_p),
                ("dwItemData",    ctypes.c_size_t),
                ("dwTypeData",    ctypes.c_wchar_p),
                ("cch",           ctypes.c_uint),
                ("hbmpItem",      ctypes.c_void_p),
            ]

        MIIM_FTYPE  = 0x00000100
        MIIM_ID     = 0x00000002
        MIIM_STRING = 0x00000040
        MFT_STRING  = 0x00000000
        MFT_SEP     = 0x00000800

        def _make_item(uid, text):
            # 使用 create_unicode_buffer 確保字串在 TrackPopupMenu 期間不被 GC
            buf = ctypes.create_unicode_buffer(text)
            mii = MENUITEMINFOW()
            mii.cbSize = ctypes.sizeof(MENUITEMINFOW)
            mii.fMask  = MIIM_ID | MIIM_STRING | MIIM_FTYPE
            mii.fType  = MFT_STRING
            mii.wID    = uid
            mii.dwTypeData = ctypes.cast(buf, ctypes.c_wchar_p)
            mii.cch    = len(text)
            return mii, buf  # 必須同時回傳 buf 防 GC

        def _make_sep():
            mii = MENUITEMINFOW()
            mii.cbSize = ctypes.sizeof(MENUITEMINFOW)
            mii.fMask  = MIIM_FTYPE
            mii.fType  = MFT_SEP
            return mii

        mii_show, buf_show = _make_item(1, self._label_show or "Show")
        mii_sep  = _make_sep()
        mii_quit, buf_quit = _make_item(2, self._label_quit or "Quit")

        user32.InsertMenuItemW(hmenu, 0, True, ctypes.byref(mii_show))
        user32.InsertMenuItemW(hmenu, 1, True, ctypes.byref(mii_sep))
        user32.InsertMenuItemW(hmenu, 2, True, ctypes.byref(mii_quit))

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)

        TPM_RIGHTBUTTON = 0x0002
        TPM_RETURNCMD   = 0x0100
        cmd = user32.TrackPopupMenu(
            hmenu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD,
            pt.x, pt.y, 0, hwnd, None)
        user32.DestroyMenu(hmenu)

        if cmd == 1 and self._on_show:
            self._on_show()
        elif cmd == 2 and self._on_quit:
            self._on_quit()
from tkinter import messagebox, scrolledtext, ttk

import sounddevice as sd

import i18n
from receiver import AudioReceiver
from sender import AudioSender
from win_audio import get_default_audio_device_name, set_default_audio_device_by_name


def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "未知"


_BUNDLED_CONFIG_FILE = pathlib.Path(__file__).resolve().parent / "app_config.json"


def _resolve_config_file() -> pathlib.Path:
    """Resolve a writable config path.

    Source runs keep using the local project file. Frozen builds (EXE/installer)
    use per-user AppData so settings survive relaunch and avoid permission issues.
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        base = pathlib.Path(appdata) if appdata else (pathlib.Path.home() / "AppData" / "Roaming")
        cfg_dir = base / "SoundConnector"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / "app_config.json"
    return _BUNDLED_CONFIG_FILE


_CONFIG_FILE = _resolve_config_file()


def _read_json_file(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ──────────────────────────────────────────────────────────────────────────────
# 主應用程式
# ──────────────────────────────────────────────────────────────────────────────

class SoundConnectorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SoundConnector")
        self.root.geometry("820x660")
        self.root.minsize(680, 560)
        self.root.resizable(True, True)

        # 設定視窗圖示（標題列 + 工作列）
        self._app_icon_photo = None
        if _PIL_OK and _ICON_FILE.exists():
            try:
                import sys
                _pil = _PILImage.open(_ICON_FILE).convert("RGBA")
                # iconphoto 設定標題列（跨平台均有效）
                _ph32 = _PILImageTk.PhotoImage(_pil.resize((32, 32), _PILImage.LANCZOS))
                _ph16 = _PILImageTk.PhotoImage(_pil.resize((16, 16), _PILImage.LANCZOS))
                self._app_icon_photo = (_ph32, _ph16)  # 防 GC
                self.root.iconphoto(True, _ph32, _ph16)
                # Windows：直接用原 .ico 設定 iconbitmap 及 AppUserModelID
                if sys.platform == "win32":
                    import ctypes
                    try:
                        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                            "net.php-pie.SoundConnector")
                    except Exception:
                        pass
                    try:
                        self.root.iconbitmap(str(_ICON_FILE))
                    except Exception:
                        pass  # iconphoto 已設定，工作列降級無妨
            except Exception:
                pass
        elif _ICON_FILE.exists():
            # 未安裝 Pillow 時，Windows 可直接使用 .ico
            try:
                self.root.iconbitmap(str(_ICON_FILE))
            except Exception:
                pass

        self._receiver: AudioReceiver | None = None
        self._sender: dict | None = None   # 單一傳送端設定
        self._is_startup_launch = "--startup-launch" in sys.argv
        self._default_port = "7355"
        self._lang = i18n.DEFAULT_LANG
        self._autostart = False
        self._autostart_recv = False
        self._autostart_send = False
        self._launch_recv = False   # 程式啟動就自動開始接收
        self._launch_send = False   # 程式啟動就自動開始傳送
        self._start_minimized = False
        self._tray_enabled = False
        self._confirm_on_exit = True
        self._remember_history = False
        self._conn_history: list[dict] = []
        self._tray_icon = None
        self._window_ready = False  # 防止啟動期 Unmap 誤觸發系統匣
        self._last_pos: dict | None = None  # <Configure> 緩存的最後位置
        self._out_device_index_map: dict[str, int] = {}
        self._in_device_index_map: dict[str, int] = {}
        self._preferred_output_device_name: str = ""

        self._load_geometry()   # 先讀記得的語言再建 UI
        self._apply_autostart(self._autostart)  # 啟動時同步修正登錄檔狀態
        self._build_ui()

    def _schedule_ui(self, fn):
        """安全地將工作排到 Tk 主執行緒。

        系統匣在背景執行緒運作；若主迴圈已結束，root.after 會拋 RuntimeError。
        這裡統一吞掉該狀況，避免關閉流程噴 traceback。
        """
        try:
            if not self.root.winfo_exists():
                return
            self.root.after(0, fn)
        except RuntimeError:
            return
        except tk.TclError:
            return

    def _t(self, key: str, **kw) -> str:
        return i18n.get(self._lang, key, **kw)

    # ── UI 建構 ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # 全域 ttk 字體設定
        _style = ttk.Style()
        _style.configure(".", font=("Segoe UI", 12))
        _style.configure("TEntry", font=("Segoe UI", 12))
        _style.configure("TCombobox", font=("Segoe UI", 12))
        _style.configure("Treeview", font=("Segoe UI", 12), rowheight=28)
        _style.configure("Treeview.Heading", font=("Segoe UI", 12, "bold"))

        local_ip = _get_local_ip()
        self.root.title(f"{self._t('app_title')}  —  {local_ip}")
        self._build_menubar()

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._notebook = nb

        recv_tab = ttk.Frame(nb)
        nb.add(recv_tab, text=self._t("tab_receiver"))
        self._build_receiver_tab(recv_tab)

        send_tab = ttk.Frame(nb)
        nb.add(send_tab, text=self._t("tab_sender"))
        self._build_sender_tab(send_tab)

        dev_tab = ttk.Frame(nb)
        nb.add(dev_tab, text=self._t("tab_devices"))
        self._build_devices_tab(dev_tab)

    def _rebuild_ui(self):
        """切換語言後銷毀並重建所有 UI（保留執行中的 sender/receiver）。"""
        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui()

    # ── 選單列 ─────────────────────────────────────────────────────────────────

    def _build_menubar(self):
        menubar = tk.Menu(self.root)

        sys_menu = tk.Menu(menubar, tearoff=False)
        sys_menu.add_command(label=self._t("menu_settings"), command=self._open_settings)
        sys_menu.add_separator()
        sys_menu.add_command(label=self._t("menu_close_window"), command=self._on_close)
        sys_menu.add_command(label=self._t("menu_quit"), command=self._quit_app)
        menubar.add_cascade(label=self._t("menu_system"), menu=sys_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label=self._t("menu_about"), command=self._show_about)
        menubar.add_cascade(label=self._t("menu_help"), menu=help_menu)

        self.root.configure(menu=menubar)

    def _open_settings(self):
        base_w = 400

        win = tk.Toplevel(self.root)
        win.title(self._t("settings_title"))
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        self.root.update_idletasks()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()

        # ── 每一行都是獨立 Frame，互不影響 ──────────────────────────────────

        # 行 1：預設埠號
        row1 = tk.Frame(win, height=50)
        row1.pack(fill="x", padx=20, pady=(16, 0))
        row1.pack_propagate(False)
        tk.Label(row1, text=self._t("settings_port"), anchor="w", font=("Segoe UI", 12)).pack(side="left")
        port_var = tk.StringVar(value=self._default_port)
        ttk.Entry(row1, textvariable=port_var, width=10).pack(side="left", padx=(8, 0))

        # 行 2：語言
        row2 = tk.Frame(win, height=50)
        row2.pack(fill="x", padx=20)
        row2.pack_propagate(False)
        tk.Label(row2, text=self._t("settings_language"), anchor="w", font=("Segoe UI", 12)).pack(side="left")
        lang_names = list(i18n.LANG_NAMES.values())
        lang_codes = list(i18n.LANG_NAMES.keys())
        lang_var = tk.StringVar(value=i18n.LANG_NAMES[self._lang])
        lang_cb = ttk.Combobox(row2, textvariable=lang_var,
                               values=lang_names, state="readonly", width=14)
        lang_cb.pack(side="left", padx=(8, 0))

        # 行 2.5：記住使用紀錄
        row_hist = tk.Frame(win, height=40)
        row_hist.pack(fill="x", padx=20)
        row_hist.pack_propagate(False)
        remember_history_var = tk.BooleanVar(value=self._remember_history)
        ttk.Checkbutton(row_hist, text=self._t("settings_remember_history"),
                        variable=remember_history_var).pack(side="left", anchor="w")

        # 行 3：開機自動啟動
        row_cb1 = tk.Frame(win, height=40)
        row_cb1.pack(fill="x", padx=20)
        row_cb1.pack_propagate(False)
        autostart_var = tk.BooleanVar(value=self._autostart)
        ttk.Checkbutton(row_cb1, text=self._t("settings_autostart"),
                        variable=autostart_var).pack(side="left", anchor="w")

        # 行 3.1：開機自啟的子功能（僅在開機自啟啟用時可設定）
        row_cb1_recv = tk.Frame(win, height=34)
        row_cb1_recv.pack(fill="x", padx=40)
        row_cb1_recv.pack_propagate(False)
        autostart_recv_var = tk.BooleanVar(value=self._autostart_recv)
        autostart_recv_chk = ttk.Checkbutton(
            row_cb1_recv,
            text=self._t("settings_autostart_recv"),
            variable=autostart_recv_var,
        )
        autostart_recv_chk.pack(side="left", anchor="w")

        row_cb1_send = tk.Frame(win, height=34)
        row_cb1_send.pack(fill="x", padx=40)
        row_cb1_send.pack_propagate(False)
        autostart_send_var = tk.BooleanVar(value=self._autostart_send)
        autostart_send_chk = ttk.Checkbutton(
            row_cb1_send,
            text=self._t("settings_autostart_send"),
            variable=autostart_send_var,
        )
        autostart_send_chk.pack(side="left", anchor="w")

        def _sync_autostart_children(*_):
            enabled = autostart_var.get()
            recv_state = "normal" if enabled else "disabled"
            # 自動傳送依賴「前一次連線紀錄」；若無紀錄則不可勾選。
            send_state = "normal" if (enabled and bool(self._conn_history)) else "disabled"
            autostart_recv_chk.configure(state=recv_state)
            autostart_send_chk.configure(state=send_state)
            if not enabled:
                autostart_recv_var.set(False)
                autostart_send_var.set(False)
            elif not self._conn_history:
                autostart_send_var.set(False)

        autostart_var.trace_add("write", _sync_autostart_children)
        _sync_autostart_children()

        # 行 3.5：程式啟動時自動開始（與開機自啟無關）
        row_launch_sep = tk.Frame(win, height=1, bg="#DDDDDD")
        row_launch_sep.pack(fill="x", padx=20, pady=(4, 0))

        row_launch_recv = tk.Frame(win, height=40)
        row_launch_recv.pack(fill="x", padx=20)
        row_launch_recv.pack_propagate(False)
        launch_recv_var = tk.BooleanVar(value=self._launch_recv)
        launch_recv_chk = ttk.Checkbutton(
            row_launch_recv,
            text=self._t("settings_launch_recv"),
            variable=launch_recv_var,
        )
        launch_recv_chk.pack(side="left", anchor="w")

        row_launch_send = tk.Frame(win, height=40)
        row_launch_send.pack(fill="x", padx=20)
        row_launch_send.pack_propagate(False)
        launch_send_var = tk.BooleanVar(value=self._launch_send)
        launch_send_chk = ttk.Checkbutton(
            row_launch_send,
            text=self._t("settings_launch_send"),
            variable=launch_send_var,
            state="normal" if self._conn_history else "disabled",
        )
        launch_send_chk.pack(side="left", anchor="w")
        if not self._conn_history:
            launch_send_var.set(False)

        # 行 4：啟動後最小化
        row_cb2 = tk.Frame(win, height=40)
        row_cb2.pack(fill="x", padx=20)
        row_cb2.pack_propagate(False)
        start_min_var = tk.BooleanVar(value=self._start_minimized)
        ttk.Checkbutton(row_cb2, text=self._t("settings_start_minimized"),
                        variable=start_min_var).pack(side="left", anchor="w")

        # 行 5：常駐系統匠
        row_cb3 = tk.Frame(win, height=40)
        row_cb3.pack(fill="x", padx=20)
        row_cb3.pack_propagate(False)
        tray_var = tk.BooleanVar(value=self._tray_enabled)
        ttk.Checkbutton(row_cb3, text=self._t("settings_tray"),
                        variable=tray_var).pack(side="left", anchor="w")

        # 行 6：關閉程式前確認
        row_cb4 = tk.Frame(win, height=40)
        row_cb4.pack(fill="x", padx=20)
        row_cb4.pack_propagate(False)
        confirm_exit_var = tk.BooleanVar(value=self._confirm_on_exit)
        ttk.Checkbutton(row_cb4, text=self._t("settings_confirm_exit"),
                variable=confirm_exit_var).pack(side="left", anchor="w")

        # 訊息標籤（錯誤/提示）— 有內容才動態顯示，否則不佔空間
        msg_lbl = tk.Label(win, text="", font=("Segoe UI", 11), anchor="w")

        def _fit_settings_window(recenter=False):
            win.update_idletasks()
            row_required_widths = [
                20 * 2 + row1.winfo_reqwidth(),
                20 * 2 + row2.winfo_reqwidth(),
                20 * 2 + row_hist.winfo_reqwidth(),
                20 * 2 + row_cb1.winfo_reqwidth(),
                40 * 2 + autostart_recv_chk.winfo_reqwidth(),
                40 * 2 + autostart_send_chk.winfo_reqwidth(),
                20 * 2 + row_launch_recv.winfo_reqwidth(),
                20 * 2 + row_launch_send.winfo_reqwidth(),
                20 * 2 + row_cb2.winfo_reqwidth(),
                20 * 2 + row_cb3.winfo_reqwidth(),
                20 * 2 + row_cb4.winfo_reqwidth(),
                20 * 2 + row5.winfo_reqwidth(),
            ]
            if msg_lbl.winfo_ismapped():
                row_required_widths.append(20 * 2 + msg_lbl.winfo_reqwidth())
            req_w = max(base_w, *row_required_widths)
            req_h = win.winfo_reqheight()
            if recenter:
                x = rx + (rw - req_w) // 2
                y = ry + (rh - req_h) // 2
                win.geometry(f"{req_w}x{req_h}+{x}+{y}")
            else:
                win.geometry(f"{req_w}x{req_h}")

        def _show_msg(text, color="red"):
            msg_lbl.configure(text=text, foreground=color)
            if text:
                msg_lbl.pack(fill="x", padx=20, before=row5)
            else:
                msg_lbl.pack_forget()
            _fit_settings_window()

        def _on_lang_change(*_):
            changed = lang_codes[lang_names.index(lang_var.get())] != self._lang
            _show_msg(self._t("settings_restart_hint") if changed else "", "gray")
        lang_cb.bind("<<ComboboxSelected>>", _on_lang_change)

        def _save():
            try:
                p = int(port_var.get().strip())
                if not (1 <= p <= 65535):
                    raise ValueError
            except ValueError:
                _show_msg(self._t("settings_port_err"), "red")
                return
            self._default_port = str(p)
            new_lang = lang_codes[lang_names.index(lang_var.get())]
            lang_changed = new_lang != self._lang
            self._lang = new_lang
            self._autostart = autostart_var.get()
            self._autostart_recv = self._autostart and autostart_recv_var.get()
            self._autostart_send = self._autostart and autostart_send_var.get() and bool(self._conn_history)
            self._launch_recv = launch_recv_var.get()
            self._launch_send = launch_send_var.get() and bool(self._conn_history)
            self._start_minimized = start_min_var.get()
            self._tray_enabled = tray_var.get()
            self._confirm_on_exit = confirm_exit_var.get()
            self._remember_history = remember_history_var.get()
            self._apply_autostart(self._autostart)
            self._apply_tray_mode(self._tray_enabled)
            self._persist_settings()
            win.destroy()
            if lang_changed:
                self._rebuild_ui()

        # 行 5：按鈕（獨立區塊，固定高度）
        row5 = tk.Frame(win, height=54)
        row5.pack(fill="x", padx=20, pady=(8, 16))
        row5.pack_propagate(False)
        ttk.Button(row5, text=self._t("settings_cancel"),
                   command=win.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(row5, text=self._t("settings_save"),
                   command=_save).pack(side="right")

        # 依內容動態計算視窗大小並置中
        _fit_settings_window(recenter=True)

    def _show_about(self):
        _URL = "https://php-pie.net"

        win = tk.Toplevel(self.root)
        win.title(self._t("about_title"))
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        frm = ttk.Frame(win, padding=(24, 20))
        frm.pack(fill="both", expand=True)

        # Logo 圖片（tk.Label 的 alpha 透明區域會顯示系統底色，與 ttk.Frame 相同）
        if _PIL_OK and _ICON_FILE.exists():
            try:
                _raw = _PILImage.open(_ICON_FILE).convert("RGBA").resize(
                    (80, 80), _PILImage.LANCZOS)
                _logo_photo = _PILImageTk.PhotoImage(_raw)
                logo_lbl = tk.Label(frm, image=_logo_photo, bd=0, highlightthickness=0)
                logo_lbl.image = _logo_photo  # 防 GC
                logo_lbl.pack(pady=(0, 8))
            except Exception:
                pass

        ttk.Label(frm, text="SoundConnector  v 1.0",
                  font=("Segoe UI", 16, "bold")).pack()
        ttk.Label(frm, text=self._t("about_subtitle"),
                  foreground="gray").pack(pady=(2, 10))
        ttk.Separator(frm, orient="horizontal").pack(fill="x")
        ttk.Label(frm, text=self._t("about_desc"),
                  wraplength=360, justify="center",
                  foreground="#555555", font=("Segoe UI", 12)).pack(pady=(8, 4))

        # ── 作者資訊區（左對齊 grid）──────────────────────────────────────
        _DONATE_URL = "https://p.ecpay.com.tw/36FF207"
        _GITHUB_URL = "https://github.com/takan003"
        info_frm = tk.Frame(frm)
        info_frm.pack(anchor="w", padx=20, pady=(4, 0))

        def _row(label_text, link_text=None, url=None, row=0):
            tk.Label(info_frm, text=label_text,
                     font=("Segoe UI", 12), foreground="#555555",
                     anchor="w").grid(row=row, column=0, sticky="w")
            if link_text:
                if url:
                    lbl = tk.Label(info_frm, text=link_text,
                                   fg="#0067C0", cursor="hand2",
                                   font=("Segoe UI", 12, "underline"), anchor="w")
                    lbl.bind("<Button-1>", lambda _, u=url: webbrowser.open(u))
                else:
                    lbl = tk.Label(info_frm, text=link_text,
                                   font=("Segoe UI", 12), foreground="#333333",
                                   anchor="w")
                lbl.grid(row=row, column=1, sticky="w")

        _row(self._t("about_author"),
             "Chang, Chia-Cheng（張家誠）", row=0)
        _row(self._t("about_email"),
             "tkes003@gmail.com", "mailto:tkes003@gmail.com", row=1)
        _row(self._t("about_github"),
             _GITHUB_URL, _GITHUB_URL, row=2)
        _row(self._t("about_website_label"),
             _URL, _URL, row=3)
        _row(self._t("about_donate"),
             _DONATE_URL, _DONATE_URL, row=4)

        # 確定按鈕
        tk.Button(frm, text=self._t("about_ok"),
                  command=win.destroy,
                  width=14, height=2,
                  relief="flat", bg="#0067C0", fg="white",
                  activebackground="#005BA3", activeforeground="white",
                  font=("Segoe UI", 12)).pack(pady=(16, 0))

        # 自動依內容計算視窗高度並置中
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        self.root.update_idletasks()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        win.geometry(f"{w}x{h}+{rx + (rw - w) // 2}+{ry + (rh - h) // 2}")

    def _persist_settings(self):
        try:
            cfg = _read_json_file(_CONFIG_FILE)
            cfg["default_port"] = self._default_port
            cfg["lang"] = self._lang
            cfg["autostart"] = self._autostart
            cfg["autostart_recv"] = self._autostart_recv
            cfg["autostart_send"] = self._autostart_send
            cfg["start_minimized"] = self._start_minimized
            cfg["tray"] = self._tray_enabled
            cfg["confirm_on_exit"] = self._confirm_on_exit
            cfg["remember_history"] = self._remember_history
            cfg["conn_history"] = self._conn_history
            cfg["preferred_output_device_name"] = self._preferred_output_device_name
            cfg["launch_recv"] = self._launch_recv
            cfg["launch_send"] = self._launch_send
            _CONFIG_FILE.write_text(json.dumps(cfg), encoding="utf-8")
        except Exception:
            pass

    # ── 連線歷史管理 ───────────────────────────────────────────────────────────

    def _history_labels(self) -> list:
        return [f"{e['name']}  —  {e['host']}:{e['port']}"
                for e in self._conn_history]

    def _save_conn_to_history(self, name: str, host: str, port: str):
        """若 remember_history 已啟用，將此筆連線資料存入歷史（以 IP 去重，最多 10 筆）。"""
        if not self._remember_history:
            return
        entry = {"name": name, "host": host, "port": port}
        # 以 IP(host) 為鍵去除重複，同一台電腦只保留最新一筆
        self._conn_history = [e for e in self._conn_history if e["host"] != host]
        self._conn_history.insert(0, entry)
        if len(self._conn_history) > 10:
            self._conn_history = self._conn_history[:10]
        self._persist_settings()
        self._refresh_history_combo()

    def _refresh_history_combo(self):
        """更新傳送端頁籤歷史下拉選單的選項清單。"""
        if self._sender and "history_cb" in self._sender:
            labels = self._history_labels()
            cb = self._sender["history_cb"]
            cb["values"] = labels
            cb.configure(state="readonly" if labels else "disabled")
            if "history_del_btn" in self._sender:
                self._sender["history_del_btn"].configure(state="normal" if labels else "disabled")
            if "history_clear_btn" in self._sender:
                self._sender["history_clear_btn"].configure(state="normal" if labels else "disabled")

    def _delete_selected_history(self, slot: dict):
        """刪除目前下拉選單選到的歷史紀錄。"""
        cb = slot.get("history_cb")
        if cb is None:
            return

        idx = cb.current()
        if not (0 <= idx < len(self._conn_history)):
            self._append_log(self.send_log, self._t("send_history_delete_select"))
            return

        removed = self._conn_history.pop(idx)
        self._persist_settings()
        self._refresh_history_combo()

        labels = self._history_labels()
        if labels:
            next_idx = min(idx, len(labels) - 1)
            cb.current(next_idx)
            e = self._conn_history[next_idx]
            slot["name_var"].set(e["name"])
            slot["host_var"].set(e["host"])
            slot["port_var"].set(e["port"])
        else:
            cb.set("")
            slot["name_var"].set(socket.gethostname())
            slot["host_var"].set("")
            slot["port_var"].set(self._default_port)

        self._append_log(
            self.send_log,
            self._t("send_history_deleted", host=removed["host"], port=removed["port"]),
        )

    def _clear_all_history(self, slot: dict):
        """清空所有歷史紀錄。"""
        if not self._conn_history:
            self._append_log(self.send_log, self._t("send_history_delete_select"))
            return

        ok = messagebox.askyesno(
            self._t("send_history_clear_confirm_title"),
            self._t("send_history_clear_confirm_msg"),
            parent=self.root,
        )
        if not ok:
            return

        self._conn_history.clear()
        self._persist_settings()
        self._refresh_history_combo()

        cb = slot.get("history_cb")
        if cb is not None:
            cb.set("")
        slot["name_var"].set(socket.gethostname())
        slot["host_var"].set("")
        slot["port_var"].set(self._default_port)

        self._append_log(self.send_log, self._t("send_history_cleared"))

    # ── 接收端頁籤 ─────────────────────────────────────────────────────────────

    def _build_receiver_tab(self, parent):
        # 設定區
        cfg = ttk.LabelFrame(parent, text=self._t("recv_settings"), padding=(12, 8))
        cfg.pack(fill="x", padx=10, pady=(10, 4))

        # 監聽 IP 固定 0.0.0.0，不對使用者顯示
        self.recv_host_var = tk.StringVar(value="0.0.0.0")

        ttk.Label(cfg, text=self._t("recv_port")).grid(row=0, column=0, sticky="w", pady=4)
        self.recv_port_var = tk.StringVar(value="7355")
        ttk.Entry(cfg, textvariable=self.recv_port_var, width=8).grid(row=0, column=1, padx=(4, 16), sticky="w")

        ttk.Label(cfg, text=self._t("recv_local_ip")).grid(row=1, column=0, sticky="w", pady=4)
        local_ip = _get_local_ip()
        self._local_ip = local_ip
        self._local_ip_var = tk.StringVar(value=local_ip)
        ttk.Entry(cfg, state="readonly",
                  textvariable=self._local_ip_var, width=16).grid(row=1, column=1, padx=(4, 8), sticky="w")
        ttk.Button(cfg, text=self._t("recv_copy"), width=6,
                   command=lambda: self._copy_to_clipboard(self._local_ip)).grid(row=1, column=2, padx=4)
        ttk.Label(cfg, text=self._t("recv_local_ip_hint"),
                  foreground="gray").grid(row=1, column=3, sticky="w")

        ttk.Label(cfg, text=self._t("recv_hostname")).grid(row=2, column=0, sticky="w", pady=(0, 4))
        self._hostname_var = tk.StringVar(value=socket.gethostname())
        ttk.Entry(cfg, state="readonly",
                  textvariable=self._hostname_var, width=24).grid(row=2, column=1, columnspan=2, padx=(4, 0), sticky="w")

        # 控制列
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill="x", padx=10, pady=6)

        self.recv_btn = ttk.Button(ctrl, text=self._t("recv_start"), width=14,
                                   command=self._toggle_receiver)
        self.recv_btn.pack(side="left")

        self.recv_status_var = tk.StringVar(value=self._t("recv_status_stopped"))
        self.recv_status_lbl = ttk.Label(ctrl, textvariable=self.recv_status_var,
                                         foreground="gray", font=("", 12, "bold"))
        self.recv_status_lbl.pack(side="left", padx=14)

        self.recv_count_var = tk.StringVar(value=self._t("recv_connected", n=0))
        ttk.Label(ctrl, textvariable=self.recv_count_var).pack(side="left")

        # 連線列表
        conn_outer = ttk.LabelFrame(parent, text=self._t("recv_connections"), padding=(6, 4))
        conn_outer.pack(fill="x", padx=10, pady=(2, 4))

        cols = ("name", "ip", "ch", "sr")
        self._recv_tree = ttk.Treeview(
            conn_outer, columns=cols, show="headings",
            height=4, selectmode="none")
        self._recv_tree.heading("name", text=self._t("recv_col_name"))
        self._recv_tree.heading("ip",   text=self._t("recv_col_ip"))
        self._recv_tree.heading("ch",   text=self._t("recv_col_ch"))
        self._recv_tree.heading("sr",   text=self._t("recv_col_sr"))
        self._recv_tree.column("name", width=140, anchor="w")
        self._recv_tree.column("ip",   width=120, anchor="w")
        self._recv_tree.column("ch",   width=50,  anchor="center")
        self._recv_tree.column("sr",   width=100, anchor="center")
        self._recv_tree.pack(fill="x")

        # 日誌區
        log_outer = ttk.LabelFrame(parent, text=self._t("recv_log"), padding=(6, 4))
        log_outer.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        self.recv_log = scrolledtext.ScrolledText(
            log_outer, state="disabled", font=("Consolas", 11), wrap="word")
        self.recv_log.pack(fill="both", expand=True)

        btn_row = ttk.Frame(log_outer)
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text=self._t("recv_clear"),
                   command=lambda: self._clear_log(self.recv_log)).pack(side="right")

    # ── 傳送端頁籤 ─────────────────────────────────────────────────────────────

    def _build_sender_tab(self, parent):
        # 若有歷史紀錄，預先填入最後一次連線的值
        _last = self._conn_history[0] if self._conn_history else {}
        self._sender = {
            "host_var":      tk.StringVar(value=_last.get("host", "")),
            "port_var":      tk.StringVar(value=_last.get("port", self._default_port)),
            "name_var":      tk.StringVar(value=_last.get("name", socket.gethostname())),
            "reconnect_var": tk.BooleanVar(value=True),
            "status_var":    tk.StringVar(value=self._t("send_status_idle")),
            "sender":        None,
        }
        slot = self._sender

        # 設定區
        cfg = ttk.LabelFrame(parent, text=self._t("send_title"), padding=(12, 8))
        cfg.pack(fill="x", padx=10, pady=(10, 4))

        # 歷史紀錄下拉列
        rh = tk.Frame(cfg, bg="#F5F5F5")
        rh.pack(fill="x", pady=(0, 6))
        tk.Label(rh, text=self._t("send_history_label"), bg="#F5F5F5",
                 font=("Segoe UI", 12)).pack(side="left")
        history_labels = self._history_labels()
        history_cb = ttk.Combobox(rh, values=history_labels,
                                  state="readonly" if history_labels else "disabled",
                                  width=36)
        history_cb.pack(side="left", padx=(2, 0))
        slot["history_cb"] = history_cb
        history_del_btn = ttk.Button(
            rh,
            text=self._t("send_history_delete"),
            width=8,
            state="normal" if history_labels else "disabled",
            command=lambda s=slot: self._delete_selected_history(s),
        )
        history_del_btn.pack(side="left", padx=(6, 0))
        slot["history_del_btn"] = history_del_btn
        history_clear_btn = ttk.Button(
            rh,
            text=self._t("send_history_clear_all"),
            width=10,
            state="normal" if history_labels else "disabled",
            command=lambda s=slot: self._clear_all_history(s),
        )
        history_clear_btn.pack(side="left", padx=(6, 0))
        slot["history_clear_btn"] = history_clear_btn

        def _on_history_select(event):
            idx = history_cb.current()
            if 0 <= idx < len(self._conn_history):
                e = self._conn_history[idx]
                slot["name_var"].set(e["name"])
                slot["host_var"].set(e["host"])
                slot["port_var"].set(e["port"])
        history_cb.bind("<<ComboboxSelected>>", _on_history_select)

        r0 = tk.Frame(cfg, bg="#F5F5F5")
        r0.pack(fill="x", pady=(0, 4))
        tk.Label(r0, text=self._t("send_name"), bg="#F5F5F5",
                 font=("Segoe UI", 12)).pack(side="left")
        name_e = ttk.Entry(r0, textvariable=slot["name_var"], width=24)
        name_e.pack(side="left", padx=(2, 0))
        slot["name_entry"] = name_e

        r1 = tk.Frame(cfg, bg="#F5F5F5")
        r1.pack(fill="x", pady=(0, 4))
        tk.Label(r1, text=self._t("send_host"), bg="#F5F5F5",
                 font=("Segoe UI", 12)).pack(side="left")
        host_e = ttk.Entry(r1, textvariable=slot["host_var"], width=20)
        host_e.pack(side="left", padx=(2, 14))
        slot["host_entry"] = host_e

        tk.Label(r1, text=self._t("send_port"), bg="#F5F5F5",
                 font=("Segoe UI", 12)).pack(side="left")
        port_e = ttk.Entry(r1, textvariable=slot["port_var"], width=8)
        port_e.pack(side="left", padx=(2, 0))
        slot["port_entry"] = port_e

        r2 = tk.Frame(cfg, bg="#F5F5F5")
        r2.pack(fill="x")
        ttk.Checkbutton(r2, text=self._t("send_reconnect"),
                        variable=slot["reconnect_var"]).pack(side="left")

        # 控制列
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill="x", padx=10, pady=6)

        btn = ttk.Button(ctrl, text=self._t("send_btn_start"), width=14,
                         command=self._toggle_sender)
        btn.pack(side="left")
        slot["btn"] = btn

        status_lbl = ttk.Label(ctrl, textvariable=slot["status_var"],
                               foreground="gray", font=("Segoe UI", 12, "bold"))
        status_lbl.pack(side="left", padx=14)
        slot["status_lbl"] = status_lbl

        peer_name_var = tk.StringVar(value="")
        slot["peer_name_var"] = peer_name_var
        peer_name_lbl = ttk.Label(ctrl, textvariable=peer_name_var,
                                  foreground="#555555", font=("Segoe UI", 11))
        peer_name_lbl.pack(side="left")
        slot["peer_name_lbl"] = peer_name_lbl

        # 日誌區
        log_outer = ttk.LabelFrame(parent, text=self._t("send_log"), padding=(6, 4))
        log_outer.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        self.send_log = scrolledtext.ScrolledText(
            log_outer, state="disabled", font=("Consolas", 11), wrap="word")
        self.send_log.pack(fill="both", expand=True)

        btn_row = ttk.Frame(log_outer)
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text=self._t("send_clear"),
                   command=lambda: self._clear_log(self.send_log)).pack(side="right")

    # ── 音訊裝置頁籤 ───────────────────────────────────────────────────────────

    def _build_devices_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(top, text=self._t("dev_title"),
                  font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text=self._t("dev_refresh"),
                   command=self._refresh_devices).pack(side="right")

        ttk.Label(parent, text=self._t("dev_hint"),
                  foreground="gray", font=("Segoe UI", 12)).pack(anchor="w", padx=10, pady=(0, 4))

        paned = ttk.PanedWindow(parent, orient="vertical")
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        out_root = tk.Frame(paned, bg="#F3F3F3")
        out_hdr = tk.Frame(out_root, bg="#0067C0", height=36)
        out_hdr.pack(fill="x")
        out_hdr.pack_propagate(False)
        tk.Label(out_hdr, text=self._t("dev_output"), bg="#0067C0", fg="white",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=12)
        self._out_count_var = tk.StringVar()
        tk.Label(out_hdr, textvariable=self._out_count_var, bg="#0067C0", fg="#AACFFF",
                 font=("Segoe UI", 11)).pack(side="right", padx=12)
        self._out_canvas, self._out_inner = self._make_scroll_pane(out_root)
        paned.add(out_root, weight=1)

        in_root = tk.Frame(paned, bg="#F3F3F3")
        in_hdr = tk.Frame(in_root, bg="#107C10", height=36)
        in_hdr.pack(fill="x")
        in_hdr.pack_propagate(False)
        tk.Label(in_hdr, text=self._t("dev_input"), bg="#107C10", fg="white",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=12)
        self._in_count_var = tk.StringVar()
        tk.Label(in_hdr, textvariable=self._in_count_var, bg="#107C10", fg="#AADDAA",
                 font=("Segoe UI", 11)).pack(side="right", padx=12)
        self._in_canvas, self._in_inner = self._make_scroll_pane(in_root)
        paned.add(in_root, weight=1)

        self._refresh_devices()

    def _make_scroll_pane(self, parent: tk.Frame):
        """建立帶捲軸的滾動區域，回傳 (canvas, inner_frame)。"""
        canvas = tk.Canvas(parent, highlightthickness=0, bg="#F3F3F3")
        vscroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg="#F3F3F3")

        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set)

        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(win_id, width=e.width),
        )
        scroll_fn = lambda e: canvas.yview_scroll(-(e.delta // 120), "units")
        canvas.bind("<MouseWheel>", scroll_fn)
        inner.bind("<MouseWheel>", scroll_fn)

        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        return canvas, inner

    def _refresh_devices(self):
        for w in self._out_inner.winfo_children():
            w.destroy()
        for w in self._in_inner.winfo_children():
            w.destroy()

        try:
            devices   = sd.query_devices()
            hostapis  = sd.query_hostapis()
            def_devs  = sd.default.device
            def_in_i  = int(def_devs[0]) if def_devs[0] is not None else -1
            def_out_i = int(def_devs[1]) if def_devs[1] is not None else -1
        except Exception as exc:
            for inner in (self._out_inner, self._in_inner):
                tk.Label(inner, text=self._t("dev_error", err=exc),
                         bg="#F3F3F3", fg="red", wraplength=200).pack(padx=12, pady=16)
            return

        _SKIP = {
            "Microsoft Sound Mapper - Input", "Microsoft Sound Mapper - Output",
            "Primary Sound Capture Driver",   "Primary Sound Driver",
        }
        _API_PRIO = {
            "Windows WASAPI": 0, "Windows DirectSound": 1,
            "MME": 2,            "Windows WDM-KS": 3,
        }

        def_out_name = self._clean_device_name(devices[def_out_i]["name"]) if def_out_i >= 0 else ""
        def_in_name  = self._clean_device_name(devices[def_in_i]["name"])  if def_in_i  >= 0 else ""

        out_names: list[str] = []
        in_names: list[str] = []
        out_meta: dict[str, tuple[int, int]] = {}
        in_meta: dict[str, tuple[int, int]] = {}

        for i, dev in enumerate(devices):
            raw_name = dev["name"]
            name = self._clean_device_name(raw_name)
            if raw_name in _SKIP:
                continue
            api  = hostapis[dev["hostapi"]]["name"]
            prio = _API_PRIO.get(api, 99)
            idx = int(dev.get("index", i))

            if dev["max_output_channels"] > 0:
                if name not in out_meta or prio < out_meta[name][0]:
                    out_meta[name] = (prio, idx)
                    if name not in out_names:
                        out_names.append(name)
            if dev["max_input_channels"] > 0:
                if name not in in_meta or prio < in_meta[name][0]:
                    in_meta[name] = (prio, idx)
                    if name not in in_names:
                        in_names.append(name)

        self._out_device_index_map = {n: meta[1] for n, meta in out_meta.items()}
        self._in_device_index_map = {n: meta[1] for n, meta in in_meta.items()}

        # 優先顯示使用者明確選定的輸出裝置，避免每次重啟後又回到系統預設。
        if self._preferred_output_device_name in self._out_device_index_map:
            def_out_name = self._preferred_output_device_name

        self._out_count_var.set(self._t("dev_count", n=len(out_names)))
        self._in_count_var.set(self._t("dev_count", n=len(in_names)))
        self._populate_device_pane(
            self._out_canvas, self._out_inner, out_names, def_out_name, "#0067C0", "output")
        self._populate_device_pane(
            self._in_canvas, self._in_inner, in_names, def_in_name, "#107C10", "input")

    def _populate_device_pane(self, canvas, inner, names, default_name, accent, kind):
        BG       = "#F3F3F3"
        CARD_BG  = "#FFFFFF"
        HOVER_BG = "#EBF3FB"

        if not names:
            tk.Label(inner, text=self._t("dev_none"), bg=BG, fg="#888888",
                     font=("Segoe UI", 12)).pack(pady=24)
            return

        tk.Frame(inner, bg=BG, height=6).pack()

        for name in names:
            is_def = (name == default_name)
            card = tk.Frame(inner, bg=CARD_BG)
            card.pack(fill="x", padx=8, pady=(0, 4))

            bar = tk.Frame(card, width=4, bg=accent if is_def else "#E8E8E8")
            bar.pack(side="left", fill="y")

            body = tk.Frame(card, bg=CARD_BG)
            body.pack(side="left", fill="x", expand=True, padx=12, pady=8)

            name_lbl = tk.Label(
                body, text=name, bg=CARD_BG, anchor="w", fg="#000000",
                font=("Segoe UI", 12, "bold" if is_def else "normal"), wraplength=0)
            name_lbl.pack(fill="x")

            if is_def:
                sub_lbl = tk.Label(body, text=self._t("dev_default"), bg=CARD_BG,
                                   fg=accent, font=("Segoe UI", 11), anchor="w")
                sub_lbl.pack(fill="x")
            else:
                sub_lbl = None

            all_w = [w for w in (card, bar, body, name_lbl, sub_lbl) if w]

            def on_enter(e, c=card, b=body, n=name_lbl, s=sub_lbl):
                c.configure(bg=HOVER_BG)
                b.configure(bg=HOVER_BG)
                n.configure(bg=HOVER_BG)
                if s: s.configure(bg=HOVER_BG)

            def on_leave(e, c=card, b=body, n=name_lbl, s=sub_lbl):
                c.configure(bg=CARD_BG)
                b.configure(bg=CARD_BG)
                n.configure(bg=CARD_BG)
                if s: s.configure(bg=CARD_BG)

            def on_click(e, k=kind, nm=name):
                self._on_device_card_click(k, nm)

            scroll_fn = lambda e, cv=canvas: cv.yview_scroll(-(e.delta // 120), "units")
            for w in all_w:
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.bind("<MouseWheel>", scroll_fn)
                w.bind("<Button-1>", on_click)
                w.configure(cursor="hand2")

        tk.Frame(inner, bg=BG, height=8).pack()

    def _on_device_card_click(self, kind: str, name: str):
        flow = "render" if kind == "output" else "capture"
        idx_map = self._out_device_index_map if kind == "output" else self._in_device_index_map
        idx = idx_map.get(name)
        if idx is None:
            return

        try:
            in_idx, out_idx = sd.default.device
            in_idx = int(in_idx) if in_idx is not None else -1
            out_idx = int(out_idx) if out_idx is not None else -1
            if kind == "output":
                sd.default.device = (in_idx, idx)
                self._preferred_output_device_name = name
                self._persist_settings()
            else:
                sd.default.device = (idx, out_idx)
        except Exception as exc:
            messagebox.showerror(
                self._t("dev_set_failed_title"),
                self._t("dev_set_failed", err=exc),
            )
            return

        if sys.platform == "win32":
            try:
                set_default_audio_device_by_name(name, flow)
            except Exception:
                pass  # PortAudio 裝置名可能被截斷，Windows COM 查不到屬正常，其餘設定仍有效

        if kind == "output" and self._receiver is not None:
                self._receiver.set_output_device(idx, name)
        # 通知本機傳送端重新選擇 Loopback 擷取裝置（輸出裝置已切換）
        if kind == "output" and self._sender:
            sender_obj = self._sender.get("sender")
            if sender_obj is not None:
                sender_obj.restart_capture()

        self._refresh_devices()

    @staticmethod
    @staticmethod
    def _clean_device_name(name: str) -> str:
        """清理 PortAudio 回傳的裝置名稱。

        處理兩類常見異常：
        1. Windows MUI 間接字串（藍芽 HFP 常見）：
           'Headset (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0 ;(DeviceName))'
           -> 'Hands-Free (DeviceName)'
        2. 空括號：'Headphones ()' -> 'Headphones'
        """
        import re
        s = name.strip()

        # MUI 間接字串偵測：包含 @...\...,#N 且有 %1...%0 的格式
        if re.search(r'@[^;(]+[,#]\d+.*?%1.*?%0', s):
            # 從 %1...%0 提取裝置類別（如 "Hands-Free"）
            type_match = re.search(r'%1\s*(.*?)\s*%0', s)
            type_str = type_match.group(1).strip() if type_match else ""

            # 提取最後一個不含 @ 的括號群組作為裝置名稱（如 "(TimeBox-audio)"）
            # 字串末端為 ...;(DeviceName)) 的結構
            dev_match = re.search(r';\s*\(([^()@][^()]*)\)\s*\)\s*$', s)
            if not dev_match:
                # fallback：取字串最末尾的 (...)
                dev_match = re.search(r'\(([^()@][^()]*)\)\s*$', s)
            device_str = dev_match.group(1).strip() if dev_match else ""

            if type_str and device_str:
                return f"{type_str} ({device_str})"
            if type_str:
                return type_str
            if device_str:
                return device_str
            return s

        # 移除尾部空括號："Headphones ()" -> "Headphones"
        s = re.sub(r'\s*\(\s*\)\s*$', '', s).strip()
        return s

    def _resolve_default_sd_index(self, kind: str):
        """Resolve preferred sounddevice index from Windows default endpoint name."""
        if sys.platform != "win32":
            return None

        flow = "render" if kind == "output" else "capture"
        try:
            win_name = get_default_audio_device_name(flow)
            if not win_name:
                return None
        except Exception:
            return None

        return self._resolve_sd_index_by_name(kind, win_name)

    def _resolve_sd_index_by_name(self, kind: str, target_name: str):
        """Resolve a sounddevice index by device name with tolerant matching."""
        if not target_name:
            return None

        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
        except Exception:
            return None

        channel_key = "max_output_channels" if kind == "output" else "max_input_channels"
        _API_PRIO = {
            "Windows WASAPI": 0,
            "Windows DirectSound": 1,
            "MME": 2,
            "Windows WDM-KS": 3,
        }

        def _norm(text: str) -> str:
            # Keep meaningful parentheses (e.g., Bluetooth model names) and
            # only normalize spaces/case to avoid false matches.
            t = (text or "").strip().lower()
            return " ".join(t.split())

        def _output_name_bias(name: str) -> int:
            n = _norm(name)
            # Bluetooth devices often expose both Stereo(A2DP) and
            # Hands-Free(HFP/AG) endpoints; prefer Stereo for playback.
            if any(k in n for k in ("hands-free", "handsfree", "ag audio", "headset")):
                return -2
            if any(k in n for k in ("stereo", "a2dp", "headphones")):
                return 1
            return 0

        target_raw = (target_name or "").strip().lower()
        best_idx = None
        best_score = -1
        best_prio = 999
        target = _norm(target_name)
        for i, dev in enumerate(devices):
            if int(dev.get(channel_key, 0)) <= 0:
                continue
            dev_name = str(dev.get("name", ""))
            raw = dev_name.strip().lower()
            cand = _norm(dev_name)
            if not cand:
                continue

            # Matching priority: exact raw > exact normalized > partial.
            score = -1
            if raw == target_raw:
                score = 3
            elif cand == target:
                score = 2
            elif target and (target in cand or cand in target):
                score = 1
            else:
                continue

            api_name = hostapis[int(dev["hostapi"])]["name"]
            prio = _API_PRIO.get(api_name, 99)
            if kind == "output":
                score += _output_name_bias(dev_name)

            # In same score tier, prefer higher-priority host API.
            if score > best_score:
                best_score = score
                best_idx = int(dev.get("index", i))
                best_prio = prio
            elif score == best_score:
                if prio < best_prio:
                    best_idx = int(dev.get("index", i))
                    best_prio = prio
        return best_idx

    # ── 接收端控制 ─────────────────────────────────────────────────────────────

    def _toggle_receiver(self):
        if self._receiver is None:
            self._start_receiver()
        else:
            self._stop_receiver()

    def _start_receiver(self):
        host = self.recv_host_var.get().strip()
        try:
            port = int(self.recv_port_var.get().strip())
        except ValueError:
            self._append_log(self.recv_log, self._t("err_port_int"))
            return

        out_idx = None
        try:
            preferred_name = self._preferred_output_device_name.strip()
            if preferred_name:
                out_idx = self._resolve_sd_index_by_name("output", preferred_name)
                if out_idx is None:
                    self._append_log(
                        self.recv_log,
                        f"[Receiver] 找不到已選輸出裝置，改用系統預設：{preferred_name}",
                    )
            if out_idx is None:
                out_idx = self._resolve_default_sd_index("output")
        except Exception:
            out_idx = None

        self._receiver = AudioReceiver(
            host=host,
            port=port,
            log_fn=lambda msg: self.root.after(0, lambda m=msg: self._append_log(self.recv_log, m)),
            count_fn=lambda n: self.root.after(
                0, lambda v=n: self.recv_count_var.set(self._t("recv_connected", n=v))),
            connections_fn=self._recv_connections_fn,
            output_device=out_idx,
            output_device_name=preferred_name if preferred_name else "",
        )
        started = self._receiver.start()
        if not started:
            err = self._receiver.last_start_error or "unknown error"
            self._append_log(self.recv_log, f"[Receiver] 啟動失敗：{err}")
            self._receiver = None
            self.recv_btn.configure(text=self._t("recv_start"))
            self._set_status(self.recv_status_var, self.recv_status_lbl,
                             self._t("recv_status_stopped"), "gray")
            return
        self.recv_btn.configure(text=self._t("recv_stop"))
        self._set_status(self.recv_status_var, self.recv_status_lbl,
                         self._t("recv_status_running"), "green")

    def _stop_receiver(self):
        if self._receiver:
            threading.Thread(target=self._receiver.stop, daemon=True).start()
            self._receiver = None
        self.recv_btn.configure(text=self._t("recv_start"))
        self._set_status(self.recv_status_var, self.recv_status_lbl,
                         self._t("recv_status_stopped"), "gray")
        self.recv_count_var.set(self._t("recv_connected", n=0))
        self._recv_tree.delete(*self._recv_tree.get_children())

    def _recv_connections_fn(self, connections: list):
        """receiver.py 呼叫，更新連線列表 Treeview。"""
        def _update():
            self._recv_tree.delete(*self._recv_tree.get_children())
            for c in connections:
                display_name = c["name"] if c["name"] else c["ip"]
                self._recv_tree.insert("", "end", values=(
                    display_name,
                    f"{c['ip']}:{c['port']}",
                    c["channels"],
                    f"{c['sample_rate']} Hz"
                ))
        self.root.after(0, _update)

    # ── 傳送端控制 ─────────────────────────────────────────────────────────────

    def _toggle_sender(self):
        slot = self._sender
        if slot["sender"] is None:
            self._start_slot(slot)
        else:
            self._stop_slot(slot)

    def _start_slot(self, slot: dict):
        host = slot["host_var"].get().strip()
        if not host:
            self._append_log(self.send_log, self._t("send_err_no_host"))
            return
        try:
            port = int(slot["port_var"].get().strip())
        except ValueError:
            self._append_log(self.send_log, self._t("send_err_bad_port"))
            return
        name = slot["name_var"].get().strip()

        tag = f"[{host}:{port}]"
        _STATUS = {
            "connecting":   (self._t("send_status_conn"),   "#C87000"),
            "connected":    (self._t("send_status_active"),  "#107C10"),
            "disconnected": (self._t("send_status_disc"),    "#CC5500"),
        }

        def on_status(state, _s=slot):
            txt, fg = _STATUS.get(state, ("●  ?", "gray"))
            def _apply():
                _s["status_var"].set(txt)
                _s["status_lbl"].configure(foreground=fg)
            self.root.after(0, _apply)

        def on_peer_name(peer_name, _s=slot):
            def _apply():
                _s["peer_name_var"].set(f"→  {peer_name}" if peer_name else "")
            self.root.after(0, _apply)

        slot["sender"] = AudioSender(
            host=host, port=port,
            reconnect=slot["reconnect_var"].get(),
            sender_name=name,
            log_fn=lambda msg, t=tag: self.root.after(
                0, lambda m=msg: self._append_log(self.send_log, f"{t} {m}")),
            status_fn=on_status,
            peer_name_fn=on_peer_name,
        )
        slot["sender"].start()
        self._save_conn_to_history(name, host, str(port))
        slot["btn"].configure(text=self._t("send_btn_stop"))
        slot["host_entry"].configure(state="disabled")
        slot["port_entry"].configure(state="disabled")
        slot["name_entry"].configure(state="disabled")
        slot["status_var"].set(self._t("send_status_conn"))
        slot["status_lbl"].configure(foreground="#C87000")

    def _stop_slot(self, slot: dict):
        if slot["sender"]:
            threading.Thread(target=slot["sender"].stop, daemon=True).start()
            slot["sender"] = None
        slot["btn"].configure(text=self._t("send_btn_start"))
        slot["host_entry"].configure(state="normal")
        slot["port_entry"].configure(state="normal")
        slot["name_entry"].configure(state="normal")
        slot["status_var"].set(self._t("send_status_idle"))
        slot["status_lbl"].configure(foreground="gray")
        slot["peer_name_var"].set("")

    # ── 工具方法 ────────────────────────────────────────────────────────────────

    def _append_log(self, widget: scrolledtext.ScrolledText, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        widget.configure(state="normal")
        widget.insert("end", f"[{ts}] {msg}\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _clear_log(self, widget: scrolledtext.ScrolledText):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _set_status(self, var: tk.StringVar, lbl: ttk.Label, text: str, color: str):
        var.set(text)
        lbl.configure(foreground=color)

    def _copy_to_clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _on_configure(self, event):
        """視窗移動或縮放時，將位置緩存到記憶體（不立即寫檔）。"""
        if event.widget is self.root and self.root.wm_state() != "withdrawn":
            x, y = self.root.winfo_x(), self.root.winfo_y()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            if x > -32000 and y > -32000:  # 排除 Windows 隱藏視窗的特殊值
                self._last_pos = {"x": x, "y": y, "width": w, "height": h}

    def _save_geometry(self):
        """將最後緩存的位置寫入設定檔（即使視窗已 withdrawn 也能正確儲存）。"""
        pos = self._last_pos
        if pos is None:
            return
        try:
            cfg = _read_json_file(_CONFIG_FILE)
            cfg.update(pos)
            _CONFIG_FILE.write_text(json.dumps(cfg), encoding="utf-8")
        except Exception:
            pass

    def _load_geometry(self):
        try:
            # Load bundled defaults first, then overlay user config.
            cfg = _read_json_file(_BUNDLED_CONFIG_FILE)
            cfg.update(_read_json_file(_CONFIG_FILE))
            w = cfg.get("width", 660)
            h = cfg.get("height", 540)
            x = cfg.get("x")
            y = cfg.get("y")
            if x is not None and y is not None:
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self.root.geometry(f"{w}x{h}")
            if "default_port" in cfg:
                self._default_port = cfg["default_port"]
            if "lang" in cfg and cfg["lang"] in i18n.TRANSLATIONS:
                self._lang = cfg["lang"]
            self._autostart = cfg.get("autostart", False)
            self._autostart_recv = cfg.get("autostart_recv", False)
            self._autostart_send = cfg.get("autostart_send", False)
            if not self._autostart:
                self._autostart_recv = False
                self._autostart_send = False
            self._start_minimized = cfg.get("start_minimized", False)
            self._tray_enabled = cfg.get("tray", False)
            self._confirm_on_exit = cfg.get("confirm_on_exit", True)
            self._remember_history = cfg.get("remember_history", False)
            self._conn_history = cfg.get("conn_history", [])
            self._preferred_output_device_name = cfg.get("preferred_output_device_name", "")
            self._launch_recv = cfg.get("launch_recv", False)
            self._launch_send = cfg.get("launch_send", False)
        except Exception:
            pass

    # ── 主迴圈 ─────────────────────────────────────────────────────────────────

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_unmap)
        self.root.bind("<Configure>", self._on_configure)
        self.root.after(200, self._set_ime_english)
        self.root.after(700, self._run_startup_actions)
        # 依設定決定是否啟用系統匣
        self.root.after(600, lambda: self._apply_tray_mode(self._tray_enabled))
        if self._start_minimized:
            # 依系統匣設定決定啟動後的最小化方式
            self.root.after(900, self._on_close)
            self.root.after(1200, self._mark_window_ready)
        else:
            # 啟動完成後才開始監聽 Unmap（防止 tkinter 初始化期誤觸）
            self.root.after(800, self._mark_window_ready)
        self.root.mainloop()

    def _mark_window_ready(self):
        self._window_ready = True

    def _set_ime_english(self):
        """將視窗的輸入法切換為英數模式。"""
        try:
            import ctypes
            hwnd = self.root.winfo_id()
            himc = ctypes.windll.imm32.ImmGetContext(hwnd)
            ctypes.windll.imm32.ImmSetConversionStatus(himc, 0, 0)
            ctypes.windll.imm32.ImmReleaseContext(hwnd, himc)
        except Exception:
            pass

    def _on_close(self):
        """WM_DELETE_WINDOW 處理：僅關閉視窗，不關閉程式。"""
        self._save_geometry()
        if self._tray_enabled:
            self.root.withdraw()
        else:
            self.root.iconify()

    def _quit_app(self, ask_confirm: bool = True):
        """真正結束程式（由功能列或系統匣菜單呼叫）。"""
        if ask_confirm and self._confirm_on_exit:
            parent = self.root if self.root.winfo_viewable() else None
            ok = messagebox.askyesno(
                self._t("quit_confirm_title"),
                self._t("quit_confirm_msg"),
                parent=parent,
            )
            if not ok:
                return

        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        self._persist_settings()   # 儲存所有設定（位置已在 _on_close 儲存）
        if self._receiver:
            threading.Thread(target=self._receiver.stop, daemon=True).start()
        if self._sender and self._sender["sender"]:
            threading.Thread(target=self._sender["sender"].stop, daemon=True).start()
        self.root.destroy()

    def _on_unmap(self, event):
        """啟用系統匣時，視窗最小化後轉為隱藏至系統匣。"""
        if event.widget is self.root and self._window_ready and self._tray_enabled:
            self.root.after(10, self.root.withdraw)

    def _minimize_to_tray(self):
        """隱藏視窗（系統匣圖示持續常駐中）。"""
        self.root.withdraw()

    def _apply_tray_mode(self, enabled: bool):
        """依設定啟用或停用系統匣常駐。"""
        if enabled:
            self._show_tray_icon()
            return

        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

        # 若當下視窗已隱藏於系統匣，關閉常駐時立即還原到工作列。
        if self.root.wm_state() == "withdrawn":
            self.root.deiconify()

    def _show_tray_icon(self):
        """建立並啟動持續常駐的系統匣圖示（純 Win32 ctypes 實作）。"""
        if self._tray_icon is not None:
            return

        if not _ICON_FILE.exists():
            return

        self._tray_icon = _WinTrayIcon(
            ico_path   = _ICON_FILE,
            tooltip    = "SoundConnector",
            label_show = self._t("tray_show"),
            label_quit = self._t("tray_quit"),
            on_show    = lambda: self._schedule_ui(self._restore_from_tray),
            on_quit    = lambda: self._schedule_ui(self._quit_app),
        )
        self._tray_icon.start()

    def _restore_from_tray(self):
        """從系統匣還原視窗。"""
        self._window_ready = True  # 確保還原後再縮小仍可進入系統匣
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _run_startup_actions(self):
        """依設定在程式啟動後自動啟動接收/傳送。

        兩種情境都會執行：
        - 開機自啟：_autostart 啟用且有 --startup-launch 參數
        - 任意啟動：_launch_recv / _launch_send 啟用（無關 is_startup_launch）
        """
        do_recv = (
            (self._launch_recv) or
            (self._autostart and self._is_startup_launch and self._autostart_recv)
        )
        do_send = (
            (self._launch_send) or
            (self._autostart and self._is_startup_launch and self._autostart_send)
        )

        if do_recv and self._receiver is None:
            self._start_receiver()

        if do_send and self._sender and self._sender["sender"] is None:
            if not self._conn_history:
                self._append_log(self.send_log, self._t("send_auto_no_history"))
                self._launch_send = False
                self._autostart_send = False
                self._persist_settings()
                return
            last = self._conn_history[0]
            self._sender["name_var"].set(last.get("name", socket.gethostname()))
            self._sender["host_var"].set(last.get("host", ""))
            self._sender["port_var"].set(last.get("port", self._default_port))
            self._start_slot(self._sender)

    def _apply_autostart(self, enable: bool):
        """透過 Windows 登錄檔設定開機自動啟動。"""
        try:
            import winreg

            # PyInstaller 打包後只需啟動 EXE；來源碼模式才需要帶上入口腳本。
            if getattr(sys, "frozen", False):
                launch_cmd = f'"{pathlib.Path(sys.executable)}" --startup-launch'
            else:
                entry = pathlib.Path(sys.argv[0]).resolve()
                launch_cmd = f'"{pathlib.Path(sys.executable)}" "{entry}" --startup-launch'

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, "SoundConnector", 0, winreg.REG_SZ, launch_cmd)
            else:
                try:
                    winreg.DeleteValue(key, "SoundConnector")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass


if __name__ == "__main__":
    SoundConnectorApp().run()
