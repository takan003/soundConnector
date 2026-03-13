"""
SoundConnector - Receiver
在有喇叭的電腦（甲）上執行，接受多個傳送端連線，混合音訊後從喇叭播放。
"""
import socket
import struct
import threading
from collections import deque

import numpy as np
import sounddevice as sd


CHUNK_FRAMES = 1024
DTYPE = "int16"
MAX_BUFFER_CHUNKS = 8  # 每個傳送端的緩衝上限（避免延遲累積）
TARGET_PEAK = 12000.0  # 目標峰值（int16 範圍內），由接收端統一整形輸出動態


class _SenderStream:
    """代表一個傳送端的音訊緩衝。"""

    def __init__(self, addr: tuple, channels: int, sample_rate: int, name: str = ""):
        self.addr = addr
        self.name = name
        self.channels = channels
        self.sample_rate = sample_rate
        self.active = True
        self._buffer: deque[np.ndarray] = deque(maxlen=MAX_BUFFER_CHUNKS)
        self._lock = threading.Lock()

    def push(self, chunk: np.ndarray):
        with self._lock:
            self._buffer.append(chunk)

    def pop(self, frames: int) -> np.ndarray:
        """取出一個 chunk；若緩衝為空則回傳靜音。"""
        with self._lock:
            if self._buffer:
                data = self._buffer.popleft()
            else:
                data = np.zeros((frames, self.channels), dtype=np.int16)
        # 確保長度符合 frames
        if data.shape[0] < frames:
            data = np.pad(data, ((0, frames - data.shape[0]), (0, 0)))
        elif data.shape[0] > frames:
            data = data[:frames]
        return data

    def __repr__(self):
        return f"<SenderStream addr={self.addr} ch={self.channels} sr={self.sample_rate}>"


class AudioReceiver:
    def __init__(self, host: str = "0.0.0.0", port: int = 7355,
                 log_fn=None, count_fn=None, connections_fn=None,
                 output_device=None, output_device_name: str = ""):
        self.host = host
        self.port = port
        self.running = False
        self._streams: list[_SenderStream] = []
        self._streams_lock = threading.Lock()
        self._playback_channels: int = 0
        self._playback_rate: int = 0
        self._output_device = output_device
        self._output_device_name: str = output_device_name
        self._agc_gain: float = 1.0
        self._output_stream: sd.OutputStream | None = None
        self._server_thread: threading.Thread | None = None
        self._ready_event = threading.Event()
        self._retry_cancel = threading.Event()
        self._start_error: str | None = None
        self._log = log_fn or print
        self._count_fn = count_fn
        self._connections_fn = connections_fn

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def start(self):
        """啟動接收伺服器（非阻塞）；回傳 True 代表監聽已就緒。"""
        self.running = True
        self._start_error = None
        self._ready_event.clear()
        self._server_thread = threading.Thread(
            target=self._accept_loop, daemon=True, name="receiver-server"
        )
        self._server_thread.start()
        self._ready_event.wait(timeout=2.5)
        if self._start_error:
            self.running = False
            return False
        if not self._ready_event.is_set():
            self._start_error = "receiver start timeout"
            self.running = False
            return False
        self._log(f"[Receiver] 監聽中 {self.host}:{self.port}，等待傳送端連線...")
        return True

    @property
    def last_start_error(self) -> str | None:
        return self._start_error

    def stop(self):
        """停止接收器與播放。"""
        self.running = False
        self._retry_cancel.set()  # 取消任何正在等待的重試
        if self._output_stream:
            self._output_stream.stop()
            self._output_stream.close()
            self._output_stream = None
        if self._server_thread:
            self._server_thread.join(timeout=3)

    @property
    def connected_count(self) -> int:
        with self._streams_lock:
            return len(self._streams)

    def set_output_device(self, output_device, device_name: str = "") -> None:
        """Update output device and (re)start playback stream."""
        # 取消前一次因裝置未就緒而啟動的重試執行緒
        self._retry_cancel.set()

        with self._streams_lock:
            self._output_device = output_device
            if device_name:
                self._output_device_name = device_name
            has_format = self._playback_channels > 0 and self._playback_rate > 0
            stream_active = self._output_stream is not None

        if not has_format:
            # Sender has not connected yet; device preference saved, will be used on first connect.
            return

        self._retry_cancel.clear()

        # 若串流已開啟，先關閉舊串流
        if stream_active:
            try:
                self._output_stream.stop()
                self._output_stream.close()
            except Exception:
                pass
            self._output_stream = None

        # 嘗試立即開啟；失敗時（例如藍芽 A2DP 尚未就緒）啟動背景重試
        try:
            self._start_playback(self._playback_channels, self._playback_rate)
            self._log("[Receiver] 輸出裝置已" + ("更新" if stream_active else "啟動"))
        except Exception as e:
            self._log(
                f"[Receiver] 輸出裝置開啟失敗，背景重試中"
                f"（若為藍芽裝置請稍候）：{e}"
            )
            threading.Thread(
                target=self._retry_start_playback,
                args=(self._playback_channels, self._playback_rate),
                daemon=True,
                name="receiver-retry",
            ).start()

    def _retry_start_playback(self, channels: int, sample_rate: int):
        """背景重試開啟輸出串流。

        藍芽 A2DP 重新協商可能需要 2-5 秒。重試前強制 PortAudio
        重新初始化，以對新連線皮求裝置狀態。
        """
        for attempt in range(7):
            # 等待 2 秒；若被取消（新的裝置選擇或 stop()）則提前退出
            if self._retry_cancel.wait(timeout=2.0):
                return
            if self._output_stream is not None:
                return  # 已由其他路徑成功啟動

            # 強制 PortAudio 重新初始化，再對新連線的藍芽裝置就能對到最新狀態
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass

            # reinit 後裝置索引可能改變，用名稱重新查找最新索引
            if self._output_device_name:
                try:
                    devices = sd.query_devices()
                    target = self._output_device_name.lower()
                    for i, dev in enumerate(devices):
                        dev_name = str(dev.get("name", "")).lower()
                        if target in dev_name or dev_name in target:
                            ch_key = "max_output_channels"
                            if int(dev.get(ch_key, 0)) > 0:
                                new_idx = int(dev.get("index", i))
                                if new_idx != self._output_device:
                                    self._log(
                                        f"[Receiver] 裝置索引更新："
                                        f"{self._output_device} → {new_idx}"
                                    )
                                    self._output_device = new_idx
                                break
                except Exception:
                    pass

            try:
                self._start_playback(channels, sample_rate)
                self._log(f"[Receiver] 輸出裝置第 {attempt + 1} 次重試成功")
                return
            except Exception as e:
                if attempt == 6:
                    self._log(f"[Receiver] 輸出裝置重試已達上限，放棄：{e}")

    # ------------------------------------------------------------------
    # 伺服器接受連線
    # ------------------------------------------------------------------

    def _accept_loop(self):
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(10)
            server.settimeout(1.0)
        except Exception as e:
            self._start_error = str(e)
            self._ready_event.set()
            self._log(f"[Receiver] 無法啟動：{e}")
            return

        self._ready_event.set()
        try:
            while self.running:
                try:
                    conn, addr = server.accept()
                    try:
                        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    except OSError:
                        pass
                    self._log(f"[Receiver] 新連線：{addr[0]}:{addr[1]}")
                    t = threading.Thread(
                        target=self._handle_sender,
                        args=(conn, addr),
                        daemon=True,
                        name=f"sender-{addr}",
                    )
                    t.start()
                except socket.timeout:
                    continue
        finally:
            server.close()

    # ------------------------------------------------------------------
    # 處理單一傳送端
    # ------------------------------------------------------------------

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> bytes:
        """確保讀取到精確的 n 個位元組。"""
        buf = bytearray()
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("連線已關閉")
            buf.extend(chunk)
        return bytes(buf)

    def _handle_sender(self, conn: socket.socket, addr: tuple):
        stream: _SenderStream | None = None
        try:
            # 讀取 12-byte 固定標頭：magic(4) + channels(2) + sample_rate(4) + name_len(2)
            raw_header = self._recv_exact(conn, 12)
            magic, channels, sample_rate, name_len = struct.unpack("!IHIH", raw_header)

            if magic != 0xC0FFEE:
                self._log(f"[Receiver] {addr} 標頭錯誤，拒絕連線")
                return

            name = ""
            if name_len > 0:
                name = self._recv_exact(conn, name_len).decode("utf-8", errors="replace")

            display = name if name else addr[0]
            self._log(f"[Receiver] {display} ({addr[0]}:{addr[1]}) — {channels} 聲道，{sample_rate} Hz")

            stream = _SenderStream(addr, channels, sample_rate, name)

            with self._streams_lock:
                # 若尚未啟動播放，以第一個串流的格式啟動
                if self._output_stream is None:
                    try:
                        self._start_playback(channels, sample_rate)
                    except Exception as e:
                        self._log(f"[Receiver] 播放串流啟動失敗：{e}")
                self._streams.append(stream)
                if self._count_fn:
                    self._count_fn(len(self._streams))
            self._notify_connections()

            # 持續接收音訊封包：length(4) + PCM data
            while self.running:
                raw_len = self._recv_exact(conn, 4)
                data_len = struct.unpack("!I", raw_len)[0]
                if data_len == 0 or data_len > 1_000_000:
                    raise ValueError(f"異常封包大小：{data_len}")
                raw_audio = self._recv_exact(conn, data_len)
                chunk = np.frombuffer(raw_audio, dtype=np.int16).reshape(-1, channels)
                stream.push(chunk)

        except (ConnectionError, OSError, ValueError) as e:
            self._log(f"[Receiver] {addr} 斷線：{e}")
        finally:
            if stream is not None:
                stream.active = False
                with self._streams_lock:
                    if stream in self._streams:
                        self._streams.remove(stream)
                    count = len(self._streams)
                if self._count_fn:
                    self._count_fn(count)
                self._notify_connections()
                self._log(f"[Receiver] {stream.name or addr[0]} 已移除（目前連線數：{self.connected_count}）")
            conn.close()

    def _notify_connections(self):
        """以目前連線清單呼叫 connections_fn。"""
        if self._connections_fn:
            with self._streams_lock:
                data = [
                    {"name": s.name, "ip": s.addr[0], "port": s.addr[1],
                     "channels": s.channels, "sample_rate": s.sample_rate}
                    for s in self._streams
                ]
            self._connections_fn(data)

    # ------------------------------------------------------------------
    # 播放輸出
    # ------------------------------------------------------------------

    def _start_playback(self, channels: int, sample_rate: int):
        """建立輸出串流，以 callback 模式播放混合音訊。

        嘗試順序：
          1. 指定裝置 + int16
          2. 指定裝置 + float32  （藍芽 A2DP 僅支援 float32）
          3. 系統預設  + int16   （最終 fallback）
        """
        self._playback_channels = channels
        self._playback_rate = sample_rate

        # 用 list 讓 closure 可以感知外部修改的 dtype
        _active_dtype: list[str] = [DTYPE]

        def callback(outdata: np.ndarray, frames: int, time_info, status):
            with self._streams_lock:
                active = [s for s in self._streams if s.active]

            if not active:
                outdata[:] = 0
                return

            mixed = np.zeros((frames, channels), dtype=np.float32)
            for s in active:
                mixed += s.pop(frames).astype(np.float32)

            # 自動增益整形
            peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
            if peak > 1.0:
                desired = TARGET_PEAK / peak
                desired = max(0.1, min(6.0, desired))
                self._agc_gain = (self._agc_gain * 0.9) + (desired * 0.1)
                mixed *= self._agc_gain

            # 限幅
            np.clip(mixed, -32768, 32767, out=mixed)

            # 依實際開啟的 dtype 輸出
            if _active_dtype[0] == "float32":
                outdata[:] = (mixed / 32768.0).astype(np.float32)
            else:
                outdata[:] = mixed.astype(np.int16)

        base_kwargs = {
            "channels": channels,
            "samplerate": sample_rate,
            "blocksize": CHUNK_FRAMES,
            "callback": callback,
        }

        target_device = self._output_device

        # 建立嘗試清單
        attempts: list[tuple] = []
        if target_device is not None:
            attempts.append((target_device, "int16"))
            attempts.append((target_device, "float32"))  # 藍芽 A2DP fallback
        attempts.append((None, "int16"))  # 系統預設最終 fallback

        last_error: Exception | None = None
        for dev, dtype in attempts:
            try:
                _active_dtype[0] = dtype
                kwargs = dict(base_kwargs, dtype=dtype)
                if dev is not None:
                    kwargs["device"] = dev
                stream = sd.OutputStream(**kwargs)
                stream.start()
                self._output_stream = stream
                dev_info = f"device={dev}, " if dev is not None else "系統預設, "
                self._log(
                    f"[Receiver] 播放已啟動 — {dev_info}{channels} 聲道，"
                    f"{sample_rate} Hz，{dtype}"
                )
                return
            except Exception as e:
                self._log(f"[Receiver] 嘗試 device={dev}, dtype={dtype} 失敗：{e}")
                last_error = e

        raise RuntimeError(f"無法啟動播放串流：{last_error}")
