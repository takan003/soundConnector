"""
SoundConnector — 網路音訊轉發工具

用法：
  接收端（甲，有喇叭）：
    python main.py receiver [--host 0.0.0.0] [--port 7355]

  傳送端（乙/丙，無喇叭）：
    python main.py sender --host <甲的IP> [--port 7355] [--no-reconnect]

  列出音訊裝置：
    python main.py devices
"""
import argparse
import sys
import time


def cmd_receiver(args):
    from receiver import AudioReceiver

    r = AudioReceiver(host=args.host, port=args.port)
    started = r.start()
    if not started:
        err = r.last_start_error or "unknown error"
        print(f"[Receiver] 啟動失敗：{err}")
        sys.exit(1)
    print("按 Ctrl+C 停止...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Receiver] 正在停止...")
        r.stop()
        print("[Receiver] 已停止")


def cmd_sender(args):
    from sender import AudioSender

    s = AudioSender(host=args.host, port=args.port, reconnect=not args.no_reconnect)
    s.start()
    print("按 Ctrl+C 停止...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Sender] 正在停止...")
        s.stop()
        print("[Sender] 已停止")


def cmd_devices(_args):
    from sender import list_devices

    list_devices()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="soundconnector",
        description="SoundConnector — 跨電腦網路音訊轉發工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # receiver
    p_recv = sub.add_parser("receiver", help="接收端：接收並播放多台電腦的音訊")
    p_recv.add_argument(
        "--host", default="0.0.0.0", metavar="IP",
        help="監聽的網路介面 IP（預設：0.0.0.0，表示所有介面）"
    )
    p_recv.add_argument(
        "--port", type=int, default=7355, metavar="PORT",
        help="監聽埠號（預設：7355）"
    )
    p_recv.set_defaults(func=cmd_receiver)

    # sender
    p_send = sub.add_parser("sender", help="傳送端：擷取系統音訊並傳送至接收端")
    p_send.add_argument(
        "--host", required=True, metavar="IP",
        help="接收端（甲電腦）的 IP 位址"
    )
    p_send.add_argument(
        "--port", type=int, default=7355, metavar="PORT",
        help="接收端的埠號（預設：7355）"
    )
    p_send.add_argument(
        "--no-reconnect", action="store_true",
        help="斷線後不自動重新連線"
    )
    p_send.set_defaults(func=cmd_sender)

    # devices
    p_dev = sub.add_parser("devices", help="列出所有可用的音訊裝置")
    p_dev.set_defaults(func=cmd_devices)

    return parser


def main():
    # 無引數，或包含 --startup-launch（開機自動啟動）時直接開啟視窗介面
    if len(sys.argv) == 1 or "--startup-launch" in sys.argv:
        from app import SoundConnectorApp
        try:
            SoundConnectorApp().run()
        except KeyboardInterrupt:
            # 開發時從終端按 Ctrl+C 結束 GUI，不需要顯示 traceback。
            print("\n[GUI] 已由使用者中斷")
        return

    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # 最外層保護：避免 Ctrl+C 顯示 traceback 影響測試判讀。
        print("\n[App] 已由使用者中斷")
