; ドライブ1の1セクタ（256バイト）を (HL) へ読む。
; D=トラック、E=セクタ。HLだけ256バイト進め、BC・DEは保持する。
; $FC=受信データ、$FD=送信データ、$FE=入力状態、$FF=出力制御。
read_sector:
        push bc
        ld a, $02                ; FDD側のバッファにセクタを読み込む。
        call send_command
        ld a, 1
        call send_byte
        xor a                    ; ドライブ1の内部番号は0。
        call send_byte
        ld a, d
        call send_byte
        ld a, e
        call send_byte
        ld a, $12                ; 高速転送で1回の握手につき2バイト受信。
        call send_command
        ld b, 128

receive_pair:
        ld a, $0B               ; RFDを立て、受信可能と通知する。
        out ($FF), a
wait_valid:
        ; FDDがDAVを立てるまで待つ。第1バイトを受けたらDACを返す。
        in a, ($FE)
        bit 0, a
        jr z, wait_valid
        ld a, $0A               ; RFDを下げる。
        out ($FF), a
        in a, ($FC)
        ld (hl), a
        inc hl
        ld a, $0D               ; DACを立てる。
        out ($FF), a
wait_second:
        ; DAVが下がると第2バイトが読める。
        in a, ($FE)
        bit 0, a
        jr nz, wait_second
        in a, ($FC)
        ld (hl), a
        inc hl
        ld a, $0C               ; DACを下げ、次の組を要求できる状態に戻す。
        out ($FF), a
        djnz receive_pair

        pop bc
        ret

send_command:
        ; ATNで新しいコマンドの開始を知らせる。実際の送信は共通処理。
        push af
        ld a, $0F               ; ATNを立てる。
        out ($FF), a
wait_command_ready:
        in a, ($FE)
        bit 1, a
        jr z, wait_command_ready
        ld a, $0E               ; ATNを下げる。
        out ($FF), a
        pop af
        jr send_ready

send_byte:
        ; 引数の送信ではATNを使わず、相手が受信可能になるまで待つ。
        push af
wait_ready:
        in a, ($FE)
        bit 1, a
        jr z, wait_ready
        pop af
send_ready:
        out ($FD), a
        ld a, $09               ; DAVを立て、データが有効と伝える。
        out ($FF), a
wait_acknowledge:
        in a, ($FE)
        bit 2, a
        jr z, wait_acknowledge
        ld a, $08               ; DACを確認したのでDAVを下げる。
        out ($FF), a
wait_acknowledge_clear:
        in a, ($FE)
        bit 2, a
        jr nz, wait_acknowledge_clear
        ret

advance_sector:
        ; 1トラック16セクタ。セクタ16の次は次のトラックのセクタ1。
        inc e
        ld a, e
        cp 17
        ret nz
        inc d
        ld e, 1
        ret

