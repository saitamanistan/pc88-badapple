        ORG $9000

; 差分圧縮された64×64ドットの動画をD88から再生する。
; 1セルは2×4ドット。1コマは32列×16行の512バイト。
TEXT_VRAM       EQU $F3C8
TEXT_ROWS       EQU 25
FRAME_BUFFER    EQU $A000
SECTOR_BUFFER   EQU $A200
FRAME_COLUMNS   EQU 32
FRAME_ROWS      EQU 16
ROW_STRIDE      EQU 120
TEXT_DMA_COUNT  EQU $8000 | (TEXT_ROWS * ROW_STRIDE - 1)

        ; CRTCを停止し、文字行の高さをセミグラフィックの描画高さに揃える。
        xor a
        out ($51), a
        ld a, $4E              ; 80桁。CRTCには桁数-2を渡す。
        out ($50), a
        ld a, $18              ; 25行。CRTCには行数-1を渡す。
        out ($50), a
        in a, ($40)
        bit 1, a
        jr z, high_resolution
        ld a, $07              ; 200ライン設定では1文字行に8走査線。
        out ($50), a
        ld a, $E0              ; 垂直帰線期間は8文字行分。
        jr set_retrace
high_resolution:
        ld a, $0F              ; 400ライン設定では1文字行に16走査線。
        out ($50), a
        xor a                  ; 垂直帰線期間は1文字行分。
set_retrace:
        out ($50), a
        ld a, $13              ; モノクロ属性あり。各行に20組の属性を置く。
        out ($50), a

        ; カーソルを隠し、全行を空のセミグラフィックとして初期化する。
        ld a, $80
        out ($51), a
        xor a
        out ($50), a
        out ($50), a
        ld hl, TEXT_VRAM
        ld b, TEXT_ROWS
init_row:
        ld c, 80
clear_cell:
        ld (hl), 0
        inc hl
        dec c
        jr nz, clear_cell
        ld (hl), 0              ; 第0桁から属性を適用する。
        inc hl
        ld (hl), $80            ; モノクロのセミグラフィック属性。
        inc hl
        ld c, 19
clear_attr:
        ld (hl), 80             ; 残りの属性は表示範囲外の第80桁に置く。
        inc hl
        ld (hl), 0
        inc hl
        dec c
        jr nz, clear_attr
        djnz init_row
        call start_text_display
        IF MOVIE_FM
        call fm_init
        ENDIF

loop_movie:
        ; 動画の先頭に戻す。最初のコマは全セル入りなので復元状態も戻る。
        ld de, (MOVIE_TRACK << 8) | 1
        ld (disk_position), de
        ld hl, SECTOR_BUFFER + 256  ; バッファを空とみなし、次の1バイトで補充。
        ld (stream_position), hl
        ld bc, MOVIE_FRAMES
next_frame:
        ; BCの残りコマ数を保存し、音符と画像差分を先に読み込む。
        push bc
        IF MOVIE_FM
        ld hl, fm_staging
        ld b, FM_TICKS * FM_CHANNELS
.load_music:
        call stream_byte
        ld (hl), a
        inc hl
        djnz .load_music
        ENDIF
        call decode_frame
        ; 音付きは前コマの音符が進むまで待つ。無音は垂直帰線を待つ。
        IF MOVIE_FM
        call fm_wait
        ELSE
        call wait_vblank
        ENDIF
        ld hl, FRAME_BUFFER
        ld de, TEXT_VRAM + 4 * ROW_STRIDE + 24
        ld a, FRAME_ROWS
draw_row:
        ; 連続する32セルだけコピーし、テキストVRAMの行末属性は保持。
        ld bc, FRAME_COLUMNS
        ldir
        ex de, hl
        ld bc, ROW_STRIDE - FRAME_COLUMNS
        add hl, bc
        ex de, hl
        dec a
        jr nz, draw_row
        IF MOVIE_FM
        call fm_queue
        ENDIF
        pop bc
        dec bc
        ld a, b
        or c
        jr nz, next_frame
        jr loop_movie

start_text_display:
        ; DMAの現行転送（ch2）と自動再ロード（ch3）を同じ画面先頭に揃える。
        ; 25行×120バイトを毎フレーム転送する。DMAの下位/上位選択は共通
        ; なので、各ポートに下位と上位を続けて書く。
        xor a
        out ($68), a
        ld a, LOW TEXT_VRAM
        out ($64), a
        ld a, HIGH TEXT_VRAM
        out ($64), a
        ld a, LOW TEXT_VRAM
        out ($66), a
        ld a, HIGH TEXT_VRAM
        out ($66), a
        ld a, LOW TEXT_DMA_COUNT
        out ($65), a
        ld a, HIGH TEXT_DMA_COUNT
        out ($65), a
        ld a, LOW TEXT_DMA_COUNT
        out ($67), a
        ld a, HIGH TEXT_DMA_COUNT
        out ($67), a
        ld a, $84              ; ch2を有効にし、ch3から自動再ロードする。
        out ($68), a
        ld a, $20              ; CRTCの画面表示を開始する。
        out ($51), a
        ret

decode_frame:
        ; 先頭バイトは変更区間数。0なら前のコマを維持、$FFなら全512セル。
        call stream_byte
        cp $FF
        jr z, full_frame
        or a
        ret z
        ld b, a
next_run:
        ; 変更区間は開始位置16ビット、長さ8ビット、セル値の順。
        call stream_byte
        ld e, a
        call stream_byte
        ld d, a
        ld hl, FRAME_BUFFER
        add hl, de
        call stream_byte
        ld c, a
copy_run:
        call stream_byte
        ld (hl), a
        inc hl
        dec c
        jr nz, copy_run
        djnz next_run
        ret

full_frame:
        ld hl, FRAME_BUFFER
        ld bc, FRAME_COLUMNS * FRAME_ROWS
copy_frame:
        call stream_byte
        ld (hl), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, copy_frame
        ret

; ストリームから1バイトをAに返す。セクタ末尾で次を読み込む。
; 復元側で使うBC・DE・HLは変更しない。
stream_byte:
        push hl
        ld hl, (stream_position)
        ld a, h
        cp HIGH (SECTOR_BUFFER + 256)
        jr nz, .ready
        push de
        ld hl, SECTOR_BUFFER
        ld de, (disk_position)
        call read_sector
        call advance_sector
        ld (disk_position), de
        pop de
        ld hl, SECTOR_BUFFER
.ready:
        ld a, (hl)
        inc hl
        ld (stream_position), hl
        pop hl
        ret

disk_position:   dw 0
stream_position: dw 0

wait_vblank:
        ; $40のbit 5。前回の垂直帰線が終わってから次の立ち上がりを待つ。
        in a, ($40)
        bit 5, a
        jr nz, wait_vblank
.start:
        in a, ($40)
        bit 5, a
        jr z, .start
        ret

        INCLUDE "disk_read.asm"
        IF MOVIE_FM
        INCLUDE "movie_fm.asm"
        ENDIF
