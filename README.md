<p align="center">
  <img src="soundConnector.ico" width="80" alt="SoundConnector icon"/>
</p>

<h1 align="center">SoundConnector</h1>
<p align="center">將無喇叭電腦的音訊，透過區域網路即時轉播到有喇叭的電腦　｜　Stream audio across PCs over LAN</p>
<p align="center"><a href="https://github.com/takan003/soundConnector/releases/latest">Download Latest Release</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-10%20%2F%2011-0067C0?logo=windows" />
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green" />
</p>

---

## 目錄 / Contents

- [English](#english)
- [繁體中文](#繁體中文)
- [简体中文](#简体中文)
- [日本語](#日本語)

---

## English

### What is this?

SoundConnector streams system audio from a PC without speakers to another PC with speakers over your local network — in real time.

### How to Run

#### Option 1: Installer (Recommended)

1. Download `SoundConnector_v1.0_Setup.exe`
2. Run the installer and follow the setup wizard
3. Launch **SoundConnector** from the desktop or Start Menu

#### Option 2: Portable (No Installation)

1. Download `SoundConnector.exe`
2. Double-click to run — no installation required

#### Option 3: From Source (Developers)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

### Usage

| Role | Steps |
|------|-------|
| **Receiver (PC with speakers)** | Go to the **Receiver** tab → Click **Start Receiving** → Note the IP address |
| **Sender (PC without speakers)** | Go to the **Sender** tab → Enter the Receiver's IP → Click **Send** |

Both PCs must be on the same local network.

Extra notes:
- Receiver can accept multiple senders at the same time and play mixed audio.
- In the **Audio Devices** tab, clicking a device sets it as Windows default.
- You can switch output device while Receiver is running.

### Important Behavior (Latest)

1. Close window vs close app
- Top-right `X` = close window only
- `System -> Close Program` or tray menu `Close Program` = fully exit

2. Minimize to system tray
- Tray is used only when `Minimize to system tray` is enabled
- If disabled, `X` minimizes to the taskbar

3. Startup child actions (auto receiver / auto sender)
- These run only on actual Windows startup launch
- Manual relaunch does not trigger them

4. Auto sender and history
- Auto sender requires previous connection history
- If history is empty, auto sender is turned off automatically

5. Launch behaviors (different meanings)
- `Auto-start Receiver/Sender on launch` runs whenever you open the app.
- Windows startup options run only when launched by Windows startup.

6. Sender history details
- History is saved only when `Remember connection history` is enabled.
- Same IP keeps only the latest record.
- Up to 10 records are kept.

7. Exit confirmation
- `Show confirmation before closing program` can be toggled in Settings

### Source Mode (Command Line)

You can also run by command line:

```powershell
.venv\Scripts\python.exe main.py receiver --host 0.0.0.0 --port 7355
.venv\Scripts\python.exe main.py sender --host <ReceiverIP> --port 7355
.venv\Scripts\python.exe main.py devices
```

Tips:
- Add `--no-reconnect` to sender if you do not want auto reconnect.

### Release Defaults (v1.0)

- Default language: English
- Default toggles: all unchecked, except `Show confirmation before closing program` is enabled
- Sender history: empty
- Installer: startup task option removed

### Requirements

- Windows 10 / 11 (64-bit)
- Installer / Portable: no extra software needed
- Source: Python 3.12+
- Source dependencies: `pyaudiowpatch`, `numpy`, `sounddevice`, `Pillow`

---

## 繁體中文

### 這是什麼？

SoundConnector 可以把「沒有喇叭的電腦」聲音，透過區域網路即時送到「有喇叭的電腦」播放。

白話一點：
- A 電腦有喇叭，開接收。
- B 電腦沒喇叭，開傳送。
- B 的聲音會在 A 播出來。

### 安裝 / 執行方式

#### 方式一：安裝版（推薦一般用戶）

1. 下載 `SoundConnector_v1.0_Setup.exe`
2. 雙擊執行，依精靈步驟完成安裝
3. 從桌面或開始選單開啟 **SoundConnector**

#### 方式二：免安裝版（單一執行檔）

1. 下載 `SoundConnector.exe`
2. 直接雙擊執行，無需安裝任何程式

#### 方式三：從原始碼執行（開發者）

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

### 使用方式

| 角色 | 說明 |
|------|------|
| **接收端（有喇叭的電腦）** | 切換到「接收端」頁籤 → 點「啟動接收」→ 記下畫面上的 IP 位址 |
| **傳送端（無喇叭的電腦）** | 切換到「傳送端」頁籤 → 填入接收端 IP → 點「傳送」 |

兩台電腦需在同一個區域網路（Wi-Fi 或有線網路皆可）。

補充說明：
- 接收端可同時接收多台傳送端，並混合播放聲音。
- 在「音訊裝置」頁籤點一下裝置，就會設成 Windows 預設裝置。
- 接收中也可以切換輸出裝置。

### 重要行為（最新版）

1. 關閉視窗 vs 關閉程式
- 右上角 `X` = 關閉視窗（不等於關閉程式）
- `系統 -> 關閉程式` 或 Tray 右鍵 `關閉程式` = 真正結束

2. 最小化時常駐系統匣
- 只有勾選「最小化時常駐系統匣」才會使用 Tray
- 未勾選時，`X` 只會最小化到工作列

3. 開機自啟子功能（自動接收 / 自動傳送）
- 只會在「Windows 開機自啟那次啟動」才觸發
- 一般手動關閉再開啟，不會觸發自動接收 / 自動傳送

4. 自動傳送與歷史紀錄
- 自動傳送需要「上次連線紀錄」
- 若歷史紀錄被清空，自動傳送會自動關閉，避免反覆失敗

5. 兩種「自動啟動」差異
- 「程式啟動時自動開始接收/傳送」：每次你手動開啟程式都會生效。
- 「開機自啟」相關選項：只有在 Windows 開機自動啟動那次才會生效。

6. 傳送端歷史紀錄細節
- 需先勾選「記住使用紀錄」，才會保存歷史。
- 同一個 IP 只會保留最新一筆。
- 最多保留 10 筆。

7. 關閉程式前確認
- 可在設定中開關「關閉程式前顯示確認」

### 原始碼模式（指令列）

除了圖形介面，也可以用指令列執行：

```powershell
.venv\Scripts\python.exe main.py receiver --host 0.0.0.0 --port 7355
.venv\Scripts\python.exe main.py sender --host <接收端IP> --port 7355
.venv\Scripts\python.exe main.py devices
```

補充：
- 若你不想斷線後自動重連，可在 sender 後面加 `--no-reconnect`。

### 主要功能

- 即時音訊串流，低延遲
- 圖形介面（GUI），操作簡單
- 支援繁體中文、简体中文、English、日本語
- 可設定是否使用系統匣（Tray）
- 可設定開機自動啟動、啟動後自動最小化
- 記住視窗位置與設定（含連線歷史）

### 發布預設值（v1.0）

- 預設語言：English
- 預設選項：除了「關閉程式前顯示確認」是開啟，其餘皆未勾選
- 傳送端歷史：空白
- 安裝精靈：已移除「開機時自動啟動」選項

### 系統需求

- Windows 10 / 11（64-bit）
- 安裝版 / 免安裝版：無需額外安裝任何環境
- 原始碼版：Python 3.12 以上
- 原始碼依賴套件：`pyaudiowpatch`、`numpy`、`sounddevice`、`Pillow`

---

## 简体中文

### 这是什么？

SoundConnector 让你通过局域网，把没有音箱的电脑的系统声音，实时转发到另一台有音箱的电脑播放。

### 安装 / 运行方式

#### 方式一：安装版（推荐普通用户）

1. 下载 `SoundConnector_v1.0_Setup.exe`
2. 双击运行，按向导完成安装
3. 从桌面或开始菜单打开 **SoundConnector**

#### 方式二：免安装版（单文件）

1. 下载 `SoundConnector.exe`
2. 直接双击运行，无需安装任何程序

#### 方式三：从源码运行（开发者）

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

### 使用方法

| 角色 | 说明 |
|------|------|
| **接收端（有音箱的电脑）** | 切换到「接收端」标签 → 点「开始接收」→ 记下显示的 IP 地址 |
| **发送端（无音箱的电脑）** | 切换到「发送端」标签 → 填入接收端 IP → 点「发送」 |

两台电脑需在同一局域网内。

### 重要行为（最新版）

1. 关闭窗口 vs 关闭程序
- 右上角 `X` = 只关闭窗口
- `系统 -> 关闭程序` 或托盘菜单 `关闭程序` = 真正退出

2. 最小化到系统托盘
- 只有开启 `最小化时常驻系统托盘` 才会使用托盘
- 未开启时，`X` 只会最小化到任务栏

3. 开机自启子功能（自动接收 / 自动发送）
- 仅在真正的 Windows 开机自启时触发
- 手动重开程序不会触发

4. 自动发送与历史记录
- 自动发送依赖上次连接历史
- 若历史为空，会自动关闭自动发送，避免反复失败

5. 退出确认
- 可在设置中开关 `关闭程序前显示确认`

### 发布默认值（v1.0）

- 默认语言：English
- 默认选项：除“关闭程序前显示确认”为开启外，其余均未勾选
- 发送端历史：空
- 安装器：已移除“开机时自动启动”选项

### 系统要求

- Windows 10 / 11（64 位）
- 安装版 / 免安装版：无需额外环境
- 源码版：Python 3.12 或以上
- 源码依赖包：`pyaudiowpatch`、`numpy`、`sounddevice`、`Pillow`

---

## 日本語

### これは何？

SoundConnector は、スピーカーのない PC の音声を、ローカルネットワーク経由でスピーカーのある PC にリアルタイム転送するツールです。

### 実行方法

#### 方法 1：インストーラー版（一般ユーザー向け）

1. `SoundConnector_v1.0_Setup.exe` をダウンロード
2. ダブルクリックしてウィザードに従いインストール
3. デスクトップまたはスタートメニューから **SoundConnector** を起動

#### 方法 2：ポータブル版（インストール不要）

1. `SoundConnector.exe` をダウンロード
2. ダブルクリックするだけで起動、インストール不要

#### 方法 3：ソースから実行（開発者向け）

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

### 使い方

| 役割 | 手順 |
|------|------|
| **受信側（スピーカーがある PC）** | 「受信側」タブ → 「受信開始」をクリック → 表示された IP アドレスを控える |
| **送信側（スピーカーがない PC）** | 「送信側」タブ → 受信側の IP を入力 → 「送信」をクリック |

両方の PC が同じローカルネットワークにいる必要があります。

### 重要な挙動（最新版）

1. ウィンドウを閉じる vs プログラム終了
- 右上の `X` はウィンドウを閉じるだけ
- `システム -> プログラムを終了` またはトレイの `プログラムを終了` で完全終了

2. 最小化時のシステムトレイ常駐
- `最小化時にシステムトレイに常駐` を有効にしたときだけトレイを使用
- 無効時は `X` でタスクバー最小化

3. 起動時の子機能（自動受信 / 自動送信）
- Windows の自動起動で起動した場合のみ実行
- 手動で再起動した場合は実行しない

4. 自動送信と履歴
- 自動送信には前回接続履歴が必要
- 履歴が空の場合は自動送信を自動でオフにする

5. 終了前確認
- 設定で `プログラム終了前に確認を表示` を切り替え可能

### リリース既定値（v1.0）

- 既定言語：English
- 既定設定：「終了前確認」はオン、それ以外はオフ
- 送信履歴：空
- インストーラー：起動時自動起動オプションを削除

### 動作環境

- Windows 10 / 11（64 ビット）
- インストーラー／ポータブル版：追加環境不要
- ソース版：Python 3.12 以上
- ソース版の依存パッケージ：`pyaudiowpatch`、`numpy`、`sounddevice`、`Pillow`

---

## GitHub 發布下載與驗證（建議）

### 繁體中文

建議從 GitHub Releases 同時下載：

- `SoundConnector.exe`
- `SoundConnector_v1.0_Setup.exe`
- `SHA256SUMS.txt`

用途：確認下載完整，且檔案未被修改。

Windows（PowerShell）操作：

1. 把 3 個檔案放同一個資料夾
2. 在該資料夾開啟 PowerShell
3. 執行以下指令

```powershell
Get-FileHash .\SoundConnector.exe -Algorithm SHA256
Get-FileHash .\SoundConnector_v1.0_Setup.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

4. 比對 SHA256 字串是否完全一致

一致 = 可安心使用  
不一致 = 重新下載，不建議執行

### English

When downloading from GitHub Releases, download these 3 files together:

- `SoundConnector.exe`
- `SoundConnector_v1.0_Setup.exe`
- `SHA256SUMS.txt`

Purpose: verify file integrity and detect tampering.

Windows (PowerShell):

1. Put all 3 files in the same folder
2. Open PowerShell in that folder
3. Run:

```powershell
Get-FileHash .\SoundConnector.exe -Algorithm SHA256
Get-FileHash .\SoundConnector_v1.0_Setup.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

4. Compare hashes exactly

Match = safe to use  
Mismatch = re-download, do not run

### 简体中文

建议从 GitHub Releases 同时下载这 3 个文件：

- `SoundConnector.exe`
- `SoundConnector_v1.0_Setup.exe`
- `SHA256SUMS.txt`

作用：确认下载完整，并确认文件未被篡改。

Windows（PowerShell）步骤：

1. 把 3 个文件放在同一文件夹
2. 在该文件夹打开 PowerShell
3. 执行：

```powershell
Get-FileHash .\SoundConnector.exe -Algorithm SHA256
Get-FileHash .\SoundConnector_v1.0_Setup.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

4. 对比 SHA256 是否完全一致

一致 = 可以使用  
不一致 = 重新下载，不建议运行

### 日本語

GitHub Releases からは次の 3 ファイルを一緒にダウンロードしてください。

- `SoundConnector.exe`
- `SoundConnector_v1.0_Setup.exe`
- `SHA256SUMS.txt`

目的：ダウンロード破損や改ざんの有無を確認するためです。

Windows（PowerShell）手順：

1. 3 ファイルを同じフォルダに置く
2. そのフォルダで PowerShell を開く
3. 実行：

```powershell
Get-FileHash .\SoundConnector.exe -Algorithm SHA256
Get-FileHash .\SoundConnector_v1.0_Setup.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

4. SHA256 が完全一致するか確認

一致 = 使用可能  
不一致 = 再ダウンロードし、実行しない

---

## Author

- **Chang, Chia-Cheng（張家誠）**
- Email: tkes003@gmail.com
- GitHub: https://github.com/takan003
- Website: https://php-pie.net
- Website: http://gas4u.net
