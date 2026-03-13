"""
SoundConnector - Sender
在沒有喇叭的電腦（乙/丙）上執行，將系統音訊透過 WASAPI Loopback 擷取並傳送至接收端。
"""
import socket
import struct
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio


CHUNK_FRAMES = 1024
DTYPE        = pyaudio.paInt16
RECONNECT_DELAY = 3  # 斷線後重連等待秒數
CONNECT_TIMEOUT = 5


class AudioSender:
    def __init__(self, host: str, port: int, reconnect: bool = True,
                 log_fn=None, status_fn=None, sender_name: str = "",
                 peer_name_fn=None):
        self.host = host
        self.port = port
        self.reconnect = reconnect
        self.sender_name = sender_name
        self.running = False
        self._thread: threading.Thread | None = None
        self._log = log_fn or print
        self._status_fn = status_fn  # 呼叫時傳入: "connecting"/"connected"/"disconnected"/"stopped"
        self._peer_name_fn = peer_name_fn
        self._restart_event = threading.Event()

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def start(self):
        """啟動傳送執行緒（非阻塞）。"""
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="sender-thread")
        self._thread.start()

    def stop(self):
        """停止傳送。"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)

    def restart_capture(self):
        """輸出裝置切換後，通知傳送端重新偵測並開啟對應的 Loopback 擷取裝置。"""
        self._restart_event.set()

    # ------------------------------------------------------------------
    # 內部實作
    # ------------------------------------------------------------------

    def _get_loopback_device(self, p: pyaudio.PyAudio) -> dict | None:
        """取得與預設輸出裝置對應的 WASAPI Loopback 裝置。"""
        try:
            wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            return None
        default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        # 尋找名稱包含 [Loopback] 且與預設輸出裝置同名的裝置
        target = default_out["name"]
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if (dev.get("isLoopbackDevice")
                    and dev["hostApi"] == wasapi["index"]
                    and target in dev["name"]):
                return dev
        # 找不到同名的，回傳任意一個 Loopback
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev.get("isLoopbackDevice") and dev["hostApi"] == wasapi["index"]:
                return dev
        return None

    def _connect(self) -> socket.socket | None:
        """嘗試連線至接收端，失敗時回傳 None。"""
        if self._status_fn:
            self._status_fn("connecting")

        addrs = []
        try:
            addrs = socket.getaddrinfo(
                self.host,
                self.port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except OSError as e:
            self._log(f"[Sender] 解析位址失敗 {self.host}:{self.port} — {e}")
            if self._status_fn:
                self._status_fn("disconnected")
            return None

        last_err: Exception | None = None
        for family, socktype, proto, _canon, sockaddr in addrs:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(CONNECT_TIMEOUT)
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass

            try:
                sock.connect(sockaddr)
                sock.settimeout(None)
                self._log(f"[Sender] 已連線至接收端 {self.host}:{self.port}")
                if self._status_fn:
                    self._status_fn("connected")
                return sock
            except (ConnectionRefusedError, TimeoutError, OSError) as e:
                last_err = e
                sock.close()

        try:
            raise last_err if last_err else OSError("unknown connect error")
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            self._log(f"[Sender] 無法連線至 {self.host}:{self.port} — {e}")
            if self._status_fn:
                self._status_fn("disconnected")
            return None

    def _run_loop(self):
        """連線 + 串流主迴圈，支援自動重連。"""
        while self.running:
            sock = self._connect()
            if sock is None:
                if self.reconnect:
                    self._log(f"[Sender] {RECONNECT_DELAY} 秒後重試...")
                    time.sleep(RECONNECT_DELAY)
                    continue
                else:
                    self.running = False
                    return

            try:
                self._stream_audio(sock)
            except Exception as e:
                self._log(f"[Sender] 串流中斷：{e}")
            finally:
                sock.close()

            if self.running and self.reconnect:
                # 若是主動 restart_capture 觸發，快速重連（0.3s）；否則等待正常延遲
                is_restart = self._restart_event.is_set()
                self._restart_event.clear()
                delay = 0.3 if is_restart else RECONNECT_DELAY
                self._log(f"[Sender] 連線中斷，{delay} 秒後重新連線...")
                if self._status_fn:
                    self._status_fn("disconnected")
                time.sleep(delay)
            else:
                self.running = False

    def _stream_audio(self, sock: socket.socket):
        """透過 WASAPI Loopback 擷取音訊並持續傳送。"""
        p = pyaudio.PyAudio()
        try:
            dev = self._get_loopback_device(p)
            if dev is None:
                raise RuntimeError("找不到 WASAPI Loopback 裝置，請確認系統設定中已啟用「立體聲」")

            channels    = int(dev["maxInputChannels"])
            sample_rate = int(dev["defaultSampleRate"])

            self._log(f"[Sender] 擷取裝置：{dev['name']}  聲道：{channels}  取樣率：{sample_rate} Hz")

            # 傳送設定標頭：magic(4) + channels(2) + sample_rate(4) + name_len(2) = 12 bytes
            # 後接 name_len bytes UTF-8 對方名稱
            name_bytes = (self.sender_name or "").encode("utf-8")[:64]
            header = struct.pack("!IHIH", 0xC0FFEE, channels, sample_rate, len(name_bytes))
            sock.sendall(header + name_bytes)

            stream = p.open(
                format=DTYPE,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=int(dev["index"]),
                frames_per_buffer=CHUNK_FRAMES,
            )
            try:
                while self.running:
                    if self._restart_event.is_set():
                        self._log("[Sender] 偵測到輸出裝置變更，重新選擇擷取裝置...")
                        raise OSError("restart capture")
                    raw = stream.read(CHUNK_FRAMES, exception_on_overflow=False)
                    sock.sendall(struct.pack("!I", len(raw)) + raw)
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            p.terminate()


def list_devices():
    """列出所有可用的音訊裝置（供除錯用）。"""
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        print(i, p.get_device_info_by_index(i))
    p.terminate()
