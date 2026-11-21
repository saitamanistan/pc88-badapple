        ORG $C000

        ; 起動 ROM がドライブ1の先頭セクタを $C000 に読み込む。
        ; 本体のロード範囲は $9000～$BFFF。スタックはその上に置く。
        di
        ld sp, $C400
        ld hl, $9000
        ; D がトラック番号、E がセクタ番号。各値は build.py が渡す。
        ld de, (PAYLOAD_TRACK << 8) | PAYLOAD_FIRST_SECTOR
        ld b, PAYLOAD_SECTORS

next_sector:
        ; read_sector は HL を256バイト進める。B は残りセクタ数。
        call read_sector
        call advance_sector
        djnz next_sector
        ; 本体の先頭から実行する。スタックと割り込み状態を引き継ぐ。
        jp $9000

        INCLUDE "disk_read.asm"

