# pc88-badapple

PC-8801mkIISR 向けに、Z80 アセンブリから起動可能な 2D フロッピーイメージ（`.d88`）をビルドするための開発環境および Bad Apple!!（白黒セミグラフィック動画＋YM2203 FM/SSG 音楽）再生プレーヤーです。

- **カスタム IPL ローダー (`ipl.asm`)**: 任意のトラック・セクタからトラック境界をまたいで最大 12 KiB（`9000h`〜`BFFFh`）の本体をロード
- **白黒セミグラフィック動画プレーヤー (`movie.asm`)**: 64×64 ドットの差分圧縮ストリームを D88 から逐次読み込み・再生（CRTC 80桁×25行・テキスト DMA 再初期化による黒帯・縦ずれ対策済み）
- **YM2203 FM 3 音＋SSG 3ch 打楽器ドライバ (`movie_fm.asm`)**: VRTC 割り込み駆動、同音連打リトリガー、ディレイ付きソフトビブラート、SSG ハードウェアエンベロープ打楽器対応
- **外部依存なしの Python ツール群**: Python 3 標準ライブラリのみで D88 生成・動画フレーム圧縮・Standard MIDI File (SMF) 変換を実行可能

> [!NOTE]
> このリポジトリには PC-88 ROM、M88gn 本体、および動画ファイル本体（MP4）は同梱していません。実行には別途用意した PC-88 ROM とエミュレータ（M88gn 等）が必要です。

---

## 動作要件

- **Python 3**（標準ライブラリのみ使用、`pip install` 不要）
- **sjasmplus 1.24.0**（初回ビルド時に GitHub Releases から `.tools/` へ自動取得し、SHA-256 を検証します）
- **M88gn** および対応する PC-88 ROM（動作確認は M88gn 1.4.0 / N88-BASIC V1H `-b21`）
- **FFmpeg**（任意：元動画 MP4 からフレームを再生成する場合のみ必要）

---

## ビルド・実行方法

### 共通準備（M88gn のパス指定）

`run_m88.py` は実行のたびに `.tools/` 内の一時フォルダへ `M88.exe`・ROM・D88 を複製して起動し、終了後に一時フォルダを削除するため、元の ROM や設定を汚しません。

PowerShell で環境変数 `M88_PATH` を設定しておくと、以降の起動コマンドで `--m88` を省略できます。

```powershell
$env:M88_PATH = "C:\path\to\M88.exe"
```

### 1. すぐ試す（ビルド済み D88 をそのまま起動）

ビルド済みの `build/bad-apple-fm.d88` を同梱しているため、**ビルド手順なしでそのまま起動**できます。

- **M88gn で直接開く場合**: `build/bad-apple-fm.d88` をドライブ 1 に挿入し、N88-BASIC V1H モードでリセットします。
- **ランチャー (`run_m88.py`) から起動する場合**:

```powershell
python run_m88.py --m88 C:\path\to\M88.exe
# （環境変数 M88_PATH または .env.local を設定済みなら引数不要）
python run_m88.py
```

### 2. ソースから再ビルドして起動

アセンブリや音色を修正して再ビルドする場合は、変換済みデータ（`.media/bad-apple.frames.bin`・`.media/bad-apple.fm.bin`）を同梱しているため、**FFmpeg や MIDI 変換なしで以下を実行するだけ**です。

```powershell
# ビルド（Z80 アセンブル＆D88 イメージ生成）
python build.py

# M88gn で起動
python run_m88.py
```

ワンショット実行バッチ（`run.bat`）や VS Code の `F5`（`Build and Play Bad Apple FM`）も使えます：

```powershell
.\run.bat            # Bad Apple!! FM版をビルド＆起動
.\run.bat --m88 C:\path\to\M88.exe
```

### 3. 元動画・MIDI からデータを再生成する場合（任意）

別の動画を使いたい場合や、[元の影絵 PV（Internet Archive）](https://archive.org/details/nicovideo-sm8628149) の MP4・MIDI から `.media/` のデータを作り直す場合のみ、以下を実行します。

```powershell
# 元動画から 64x64・10fps・8bit グレースケールの生フレームを抽出
ffmpeg -i bad_apple.mp4 -an -vf "fps=10,scale=64:64:force_original_aspect_ratio=decrease,pad=64:64:(ow-iw)/2:(oh-ih)/2,format=gray" -f rawvideo bad-apple.gray

# PC-88 セミグラフィック形式（512バイト/コマ）へ変換
python movie_frames.py bad-apple.gray .media/bad-apple.frames.bin

# MIDI を取得して YM2203 FM + SSG ドラムデータ（18バイト/コマ）を再生成
curl.exe -fsSL -o alstroemeria_records_bad_apple.mid https://raw.githubusercontent.com/rkk-2s/bad-apple/master/alstroemeria_records_bad_apple.mid
# （SHA-256 検証付きで取得する場合は python fetch_midi.py も利用可能）
python movie_music.py alstroemeria_records_bad_apple.mid .media/bad-apple.fm.bin --frames 2191
```

---

## `build.py` の主なオプション

```powershell
python build.py --track 3 --sector 16 --sectors 20 --output build/custom.d88
```

| オプション | 説明 |
| :--- | :--- |
| `--movie-data PATH` | `movie_frames.py` で生成した動画フレームを指定（既定: `.media/bad-apple.frames.bin`） |
| `--fm-data PATH` | `movie_music.py` で生成した FM/SSG 音符データを指定（既定: `.media/bad-apple.fm.bin`） |
| `--output PATH` | 出力する `.d88` ファイルパス（既定: `build/bad-apple-fm.d88`） |
| `--payload PATH` | 別のアセンブラ／リンカーで作った `9000h` 配置の生バイナリを指定 |
| `--track N` | 開始トラック（0〜79、既定 `0`。`シリンダ番号 × 2 + 面番号`） |
| `--sector N` | 開始セクタ（1〜16、既定 `2`。トラック 0・セクタ 1 は IPL 専用） |
| `--sectors N` | 読み込みセクタ数（最大 48 セクタ = 12 KiB、省略時は本体サイズに自動調整） |

- 旧来の IPL 単体（`C000h`、最大 256 バイト）は `python make_d88.py INPUT.bin OUTPUT.d88` で変換できます。
- IPL から本体への引き渡し仕様: 配置先 `9000h`（先頭エントリ）、最大 `12 KiB`（`9000h`〜`BFFFh`）、割り込み禁止（`DI`）、`SP = C400h`。

---

## データ形式とサウンド仕様

### 動画差分データ形式
- D88 1 枚の動画データ領域はトラック 4 以降の **304 KiB**。
- `movie_frames.py` は画素値 128 以上を白として 2×4 ドット＝1 セル（32 列×16 行＝512 バイト/コマ）にパックします。
- 各コマは 1 バイトのヘッダーから始まります：`0` = 前コマ維持、`255` = 後続 512 バイトで全セル更新、`1〜254` = 変更区間数。
- 各変更区間は開始セル位置（16bit リトルエンディアン）、長さ（8bit）、セル値列で構成され、セクタ境界をまたげます。先頭コマは常に完全フレームのため、ループ時に状態を持ち越しません。

### YM2203 FM 3 音＋SSG 3ch 打楽器仕様
- 1 コマにつき 18 バイト（3 チャンネル × 6 VRTC ティック）を動画差分の直前に格納します。
- **各バイトの構成**: 下位 7 ビット = MIDI ノート番号（`0` = 休符、`127` = 同音リトリガー）、上位 1 ビット = SSG 打楽器トリガ（Ch 0 = キック、Ch 1 = スネア、Ch 2 = ハイハット）。
- **FM 3 パート**: 主旋律（ディレイ付きソフトビブラート対応）、ベース、伴奏。
- **SSG 3 チャンネル打楽器**:
  - Ch A = キック（約 156 Hz＋SSG ハードウェアエンベロープ約 45 ms）
  - Ch B = スネア（195 Hz 胴鳴り＋中域ノイズ減衰）
  - Ch C = ハイハット（高域ノイズの短い減衰）

---

## ファイル構成

| ファイル | 内容 |
| :--- | :--- |
| `ipl.asm` | `C000h` 起動の 1 セクタ IPL ローダー |
| `disk_read.asm` | PC-88 FDD サブシステム（8255 ポート `$FC〜$FF`）共通読み込みルーチン |
| `movie.asm` | CRTC/DMA 初期化および 64×64 差分動画プレーヤー |
| `movie_fm.asm` | YM2203 FM 3 音＋SSG 3ch 打楽器 VRTC 割り込みドライバ |
| `build.py` | sjasmplus 取得・Z80 アセンブル・D88 パッケージング |
| `make_d88.py` | 2D D88 ディスクイメージ生成 |
| `movie_frames.py` | 64×64 グレースケール変換・差分圧縮エンコーダー |
| `movie_music.py` | 標準ライブラリのみの SMF パーサー・YM2203 音符データ生成 |
| `run_m88.py` | 一時複製フォルダを使った M88gn 起動ランチャー |
| `fetch_midi.py` | Bad Apple!! MIDI アレンジ（[rkk-2s/bad-apple](https://github.com/rkk-2s/bad-apple)）の取得・SHA-256 検証スクリプト |
| `build/bad-apple-fm.d88` | ビルド済み起動用 D88 イメージ（FM 音楽＋動画全 2191 コマ） |

---

## クレジット・ライセンス

- FDD 通信手順の参照: [bferguson3/pc88-asm](https://github.com/bferguson3/pc88-asm)
- `movie_fm.asm` の FM 音色パラメータの一部は以下のオープンソース音色データを利用しています：
  - Ch 0（LeadSquare）: [Wohlstand/libOPNMIDI](https://github.com/Wohlstand/libOPNMIDI) `xg.wopn`（MIT License）
  - Ch 1（`@168 ebass9`）・Ch 2（`@133 d_gtr`）: [OpenMUCOM88 (`onitama/mucom88`)](https://github.com/onitama/mucom88) `voice.dat`（CC BY-NC-SA 4.0 / `Copyright (C) by Yuzo Koshiro`）
    - ※`voice.dat` 由来の音色パラメータを含むため、非営利・表示・継承（CC BY-NC-SA 4.0）の条件に従ってください。
