; PC-8801mkIISRの標準YM2203で、FM 3音とSSG 3チャンネル打楽器を再生する。
; 動画1コマにつき6回の垂直帰線割り込みで音符を進める。
; FM音色は Wohlstand/libOPNMIDI (xg.wopn, MIT License) から採用・音量調整。
FM_TICKS       EQU 6
FM_CHANNELS    EQU 3
FM_RETRIGGER   EQU $7F
VRTC_VECTOR    EQU $A402
KICK_LEN       EQU 6
SNARE_LEN      EQU 7
HAT_LEN        EQU 2
VIB_DELAY      EQU 10

fm_init:
        ; 全FMチャンネルをキーオフし、各パートに音色を設定する。
        ld c, 0
.keyoff:
        ld a, $28
        ld e, c
        call fm_write
        inc c
        ld a, c
        cp FM_CHANNELS
        jr nz, .keyoff

        ld hl, fm_patch
.next_parameter:
        ld a, (hl)
        inc hl
        cp $FF
        jr z, .ssg_mute
        ld b, FM_CHANNELS
.channel:
        ld e, (hl)
        inc hl
        call fm_write
        inc a
        djnz .channel
        jr .next_parameter

.ssg_mute:
        ; SSG全チャンネルを消音する。
        ld a, $07
        ld e, $3F
        call fm_write
        ld a, $08
        ld e, 0
        call fm_write
        ld a, $09
        call fm_write
        ld a, $0A
        call fm_write
        ; 割り込みモード2、VRTCのベクタ02h。割り込みレベル1を有効にする。
        ld hl, fm_interrupt
        ld (VRTC_VECTOR), hl
        ld a, HIGH VRTC_VECTOR
        ld i, a
        im 2
        ld a, 2
        out ($E6), a
        out ($E4), a
        ei
        ret

fm_wait:
        ; EIの直後のHALTまで割り込みを遅延させ、待機条件の取りこぼしを防ぐ。
        di
        ld a, (fm_ticks_left)
        or a
        jr z, .empty
        ei
        halt
        jr fm_wait
.empty:
        ei
        ret

fm_queue:
        ; 残りティックが0の間に次コマの音符を再生用バッファへ移す。
        ; ポインタを設定してから残りティックを公開する。
        ld hl, fm_staging
        ld de, fm_active
        ld bc, FM_TICKS * FM_CHANNELS
        ldir
        ld hl, fm_active
        ld (fm_cursor), hl
        ld a, FM_TICKS
        ld (fm_ticks_left), a
        ret

fm_interrupt:
        ; メイン側はディスク読み込みや画像復元中なので、レジスタを退避する。
        push af
        push bc
        push de
        push hl
        ld hl, fm_ticks_left
        ld a, (hl)
        or a
        jr z, .update_fx
        dec (hl)
        ; 音符の上位ビットは打楽器トリガ。下位7ビットがFMの音程（$7Fは同音再発音）。
        ld hl, (fm_cursor)
        call ssg_drum_trigger
        ld de, fm_previous
        ld c, 0
.channel:
        ld a, (hl)
        and $7F
        cp FM_RETRIGGER
        jr nz, .normal_note
        ld a, (de)
        or a
        jr z, .next
        jr .trigger_note
.normal_note:
        ld b, a
        ld a, (de)
        cp b
        jr z, .next
        ld a, b
        ld (de), a
.trigger_note:
        push de
        push hl
        call fm_note
        pop hl
        pop de
.next:
        inc hl
        inc de
        inc c
        ld a, c
        cp FM_CHANNELS
        jr nz, .channel
        ld (fm_cursor), hl
.update_fx:
        ; ディスク読み込み待ち中でもドラム減衰とビブラートは継続する。
        call ssg_drum_update
        call lead_vibrato_update
.ack:
        ; 88の割り込みコントローラは応答時にレベルをクリアするため再設定。
        ld a, 2
        out ($E4), a
        pop hl
        pop de
        pop bc
        pop af
        ei
        reti

; 3バイトの上位ビットをそれぞれキック(Ch A)・スネア(Ch B)・ハイハット(Ch C)の
; 立ち上がりトリガとして受け取る（旧形式の連続ビットでも二重発音しない）。HLは保持する。
ssg_drum_trigger:
        push hl
        ld c, 0
        bit 7, (hl)
        jr z, .b1
        set 0, c
.b1:
        inc hl
        bit 7, (hl)
        jr z, .b2
        set 1, c
.b2:
        inc hl
        bit 7, (hl)
        jr z, .edge
        set 2, c
.edge:
        ld a, (drum_prev)
        cpl
        and c                   ; 0 -> 1 になったビットだけ抽出
        ld b, a
        ld a, c
        ld (drum_prev), a
        bit 0, b
        jr z, .check_snare
        ld a, KICK_LEN
        ld (kick_step), a
.check_snare:
        bit 1, b
        jr z, .check_hat
        ld a, SNARE_LEN
        ld (snare_step), a
.check_hat:
        bit 2, b
        jr z, .done
        ld a, HAT_LEN
        ld (hat_step), a
.done:
        pop hl
        ret

; SSG 3チャンネルの打楽器エンベロープを1ティック進める。
; C=ミキサー値($3Fから有効ビットを落とす)、B=ノイズ周期(0なら更新不要)。
ssg_drum_update:
        ld bc, $003F

        ; --- キック（SSG Ch A: 約156Hz・HWエンベロープ約45msのキレのある「トッ」） ---
        ld hl, kick_step
        ld a, (hl)
        or a
        jr nz, .kick_active
        ld a, $08
        ld e, 0
        call fm_write
        jr .snare
.kick_active:
        ; 毎ティック、kick_env のトーン周期で約325Hz→44Hzへピッチを下げる。
        dec (hl)
        ld e, a
        ld a, KICK_LEN
        sub e
        add a, a                ; A = index * 2
        ld e, a
        ld d, 0
        ld hl, kick_env
        add hl, de
        ld a, $00
        ld e, (hl)
        call fm_write
        inc hl
        ld a, $01
        ld e, (hl)
        call fm_write
        res 0, c                ; Tone A 有効
        ld a, (kick_step)
        cp KICK_LEN - 1
        jr nz, .snare
        ; 1ティック目: HWエンベロープを起動し、ノイズで短いアタッククリックを足す。
        ld a, $0B
        ld e, $C0
        call fm_write
        ld a, $0C
        ld e, $02               ; エンベロープ減衰時間 約90ms
        call fm_write
        ld a, $08
        ld e, $10               ; Ch A にハードウェアエンベロープを適用
        call fm_write
        ld a, $0D
        ld e, $09               ; 単発減衰（15→0で停止）をトリガ
        call fm_write
        res 3, c                ; Noise A 有効（クリック）
        ld b, $04               ; スネア発音時はスネア側のノイズ周期で上書き

.snare:
        ; --- スネア（SSG Ch B: アタック胴鳴り＋ノイズ減衰） ---
        ld hl, snare_step
        ld a, (hl)
        or a
        jr nz, .snare_active
        ld a, $09
        ld e, 0
        call fm_write
        jr .hat
.snare_active:
        dec (hl)
        ld e, a
        ld a, SNARE_LEN
        sub e
        add a, a
        add a, a                ; A = index * 4
        ld e, a
        ld d, 0
        ld hl, snare_env
        add hl, de
        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
        ld a, d
        or a
        jr z, .snare_noise_only
        ld a, $02
        call fm_write
        ld a, $03
        ld e, d
        call fm_write
        res 1, c                ; Tone B 有効
.snare_noise_only:
        ld a, $09
        ld e, (hl)
        call fm_write
        inc hl
        ld b, (hl)              ; ステップごとのノイズ周期（明るい→中域）
        res 4, c                ; Noise B 有効

.hat:
        ; --- ハイハット（SSG Ch C: 高域ノイズの短い「チッ」） ---
        ld hl, hat_step
        ld a, (hl)
        or a
        jr nz, .hat_active
        ld a, $0A
        ld e, 0
        call fm_write
        jr .finish_ssg
.hat_active:
        dec (hl)
        ld e, a
        ld a, HAT_LEN
        sub e
        ld e, a
        ld d, 0
        ld hl, hat_env
        add hl, de
        ld a, $0A
        ld e, (hl)
        call fm_write
        res 5, c                ; Noise C 有効
        ld a, b
        or a
        jr nz, .finish_ssg
        ld b, $01               ; ハイハット用最高域ノイズ（スネア・キック非発音時）

.finish_ssg:
        ld a, b
        or a
        jr z, .write_mixer
        ld a, $06
        ld e, b
        call fm_write
.write_mixer:
        ld a, $07
        ld e, c
        jp fm_write

; 主旋律（Ch 0）の長い伸びにだけ穏やかなソフトビブラートを掛ける。
lead_vibrato_update:
        ld a, (fm_previous)
        or a
        ret z
        ld hl, lead_age
        ld a, (hl)
        cp VIB_DELAY
        jr nc, .apply
        inc (hl)
        ret
.apply:
        ld hl, lead_vib_phase
        ld a, (hl)
        inc a
        and $0F
        ld (hl), a
        ld e, a
        ld d, 0
        ld hl, vib_table
        add hl, de
        ld a, (hl)
        ld e, a
        add a, a
        sbc a, a
        ld d, a                 ; 符号拡張したデルタをDEへ
        ld hl, (lead_base_fnum)
        add hl, de
        ld a, $A4
        ld e, h
        call fm_write
        ld a, $A0
        ld e, l
        jp fm_write

; A=MIDIノート番号（0は休符）、C=FMチャンネル。
; まず前音をキーオフし、パート別トランスポーズ後にブロックとFナンバーを書いて発音する。
fm_note:
        ld d, a
        ld a, $28
        ld e, c
        call fm_write
        ld a, d
        or a
        ret z
        ld hl, fm_transpose
        ld e, c
        ld d, 0
        add hl, de
        add a, (hl)
        cp 128
        jr c, .in_range
        ld a, 127
.in_range:
        ld l, a
        ld h, 0
        add hl, hl
        ld de, fm_pitch_table
        add hl, de
        ld e, (hl)
        inc hl
        ld d, (hl)
        ld a, c
        or a
        jr nz, .write_freq
        ld (lead_base_fnum), de
        xor a
        ld (lead_age), a
        ld (lead_vib_phase), a
.write_freq:
        ld a, $A4
        add a, c
        push de
        ld e, d
        call fm_write
        pop de
        ld a, $A0
        add a, c
        call fm_write
        ld a, $F0
        or c
        ld e, a
        ld a, $28
        jp fm_write

; A=YM2203レジスタ番号、E=値。BUSYが解除されてから書き込む。
; 8MHz機でもアドレス→データ間の待ち時間を確保しつつ、Aを保持する。
fm_write:
        push af
.wait_idle:
        in a, ($44)
        bit 7, a
        jr nz, .wait_idle
        pop af
        out ($44), a
        push af
        nop
        nop
        ld a, e
        out ($45), a
        pop af
        ret

; 各パートの音色定義。
; Ch0: Wohlstand/libOPNMIDI xg.wopn (MIT) GM #80 LeadSquare (ALG=4, FB=7)
; Ch1: MUCOM88 voice.dat @168 ebass9 (ALG=2, FB=7, +12移調) — Copyright (C) by Yuzo Koshiro
; Ch2: MUCOM88 voice.dat @133 d_gtr  (ALG=0, FB=5)         — Copyright (C) by Yuzo Koshiro
fm_patch:
        ; レジスタ番号、Ch0(主旋律)、Ch1(ベース)、Ch2(伴奏)
        db $30,$32,$60,$43, $34,$02,$60,$77, $38,$71,$62,$4F, $3C,$01,$61,$71
        ; TL: キャリアのみ調整（元値 $48 Ch0=11、$4C Ch0=15 / Ch1=12 / Ch2=20）。
        ; リードを約2dB下げ、ベースを約1.5dB上げてドラムと低域の居場所を作る。
        db $40,24,27,10,    $44,26,30,23,    $48,14,8,22,     $4C,18,10,19
        db $50,$5F,$1F,$1F, $54,$1A,$1F,$1F, $58,$1C,$9F,$12, $5C,$5B,$1F,$1F
        db $60,0,11,4,      $64,0,7,4,       $68,0,21,1,      $6C,0,13,12
        db $70,1,7,1,       $74,0,31,1,      $78,0,14,1,      $7C,0,7,0
        db $80,$8B,$58,$10, $84,$2A,$57,$10, $88,$1A,$37,$18, $8C,$0F,$57,$18
        db $B0,$3C,$3A,$28, $FF

; MUCOM88 @168 ebass9 は OP1/OP3 の MUL=0 (0.5x) を基準にするため +12 半音移調する。
fm_transpose:
        db 0, 12, 0

; SSG打楽器エンベロープ（1ステップ = 1 VRTC ティック）。
kick_env:
        ; トーン周期（約325Hz→162→98→70→54→44Hz）。音量はHWエンベロープ。
        dw $0180, $0300, $0500, $0700, $0900, $0B00
snare_env:
        ; トーン周期下位、上位（0ならノイズのみ）、音量、ノイズ周期
        db $00,$02,15,$05,  $80,$02,15,$06,  $00,$00,13,$07,  $00,$00,11,$08
        db $00,$00,8,$09,   $00,$00,5,$0A,   $00,$00,2,$0A
hat_env:
        db 7, 3

vib_table:
        db 0, 2, 4, 5, 6, 5, 4, 2, 0, -2, -4, -5, -6, -5, -4, -2

; 割り込み側への受け渡し。stagingとactiveの分離で読み込み中の更新を防ぐ。
fm_ticks_left:  db 0
fm_cursor:      dw fm_active
fm_previous:    defs FM_CHANNELS, 0
drum_prev:      db 0
kick_step:      db 0
snare_step:     db 0
hat_step:       db 0
lead_base_fnum: dw 0
lead_age:       db 0
lead_vib_phase: db 0
fm_staging:     defs FM_TICKS * FM_CHANNELS, 0
fm_active:      defs FM_TICKS * FM_CHANNELS, 0

fm_pitch_table:
        ; Windows側でMIDIノート番号ごとのYM2203周波数レジスタ値を生成する。
        INCBIN "build/fm_pitch.bin"
