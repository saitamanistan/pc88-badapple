"""Arrange the referenced Bad Apple MIDI for three YM2203 FM voices."""

import argparse
from pathlib import Path
from struct import pack, unpack_from


TICKS_PER_FRAME = 6
CHANNELS = 3
TICKS_PER_SECOND = 60
OPN_CLOCK = 3_993_600


def _read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            return value, pos


def _parse_midi(midi_path: Path) -> tuple[int, list[list[tuple[int, str, int, int, int]]]]:
    """Minimal Standard MIDI File parser (no external dependencies)."""
    data = midi_path.read_bytes()
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("not a Standard MIDI File")
    header_len, _fmt, track_count, division = unpack_from(">IHHH", data, 4)
    if division & 0x8000:
        raise ValueError("SMPTE time division is not supported")
    pos = 8 + header_len
    tracks: list[list[tuple[int, str, int, int, int]]] = []
    for _ in range(track_count):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            raise ValueError("corrupted MIDI track header")
        track_len = unpack_from(">I", data, pos + 4)[0]
        pos += 8
        end = pos + track_len
        abs_tick = 0
        running_status = 0
        track_events: list[tuple[int, str, int, int, int]] = []
        while pos < end:
            delta, pos = _read_vlq(data, pos)
            abs_tick += delta
            status = data[pos]
            if status & 0x80:
                pos += 1
                if status < 0xF0:
                    running_status = status
            else:
                status = running_status
            kind = status & 0xF0
            channel = status & 0x0F
            if kind in (0x80, 0x90):
                note, velocity = data[pos], data[pos + 1]
                pos += 2
                msg_type = "note_on" if (kind == 0x90 and velocity > 0) else "note_off"
                track_events.append((abs_tick, msg_type, channel, note, velocity))
            elif kind in (0xA0, 0xB0, 0xE0):
                pos += 2
            elif kind in (0xC0, 0xD0):
                pos += 1
            elif status == 0xFF:
                meta_type = data[pos]
                pos += 1
                length, pos = _read_vlq(data, pos)
                if meta_type == 0x51 and length == 3:
                    tempo = (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]
                    track_events.append((abs_tick, "set_tempo", 0, tempo, 0))
                pos += length
            elif status in (0xF0, 0xF7):
                length, pos = _read_vlq(data, pos)
                pos += length
            else:
                raise ValueError(f"unsupported MIDI status 0x{status:02X}")
        tracks.append(track_events)
        pos = end
    return division, tracks


def pitch_table() -> bytes:
    words = bytearray()
    for note in range(128):
        frequency = 440 * 2 ** ((note - 69) / 12)
        fnum = frequency * 144 * 2 ** 20 / OPN_CLOCK
        block = 0
        # Keep F-number below 2032 so lead software vibrato (+/-6) never overflows into Block bits.
        while fnum >= 2032 and block < 7:
            fnum /= 2
            block += 1
        words.extend(pack("<H", (block << 11) | min(round(fnum), 2031)))
    return bytes(words)


def arrange(midi_path: Path, frames: int, offset: float) -> bytes:
    ticks_per_beat, tracks = _parse_midi(midi_path)
    # Ronald Macdonald's MIDI, as distributed by rkk-2s/bad-apple.
    # Track 5 (GM #120 Guitar Fret Noise) is a 48-semitone SFX sweep, not pitched harmony.
    roles = {6: 0, 9: 0, 3: 1, 7: 2, 8: 2, 10: 2, 11: 2, 1: 3, 4: 3}
    if len(tracks) <= max(roles):
        raise ValueError("expected the Ronald Macdonald Bad Apple arrangement")
    messages = []
    for track_index, track in enumerate(tracks):
        for abs_tick, msg_type, channel, value, _velocity in track:
            if msg_type == "set_tempo" or (
                track_index in roles and msg_type in ("note_on", "note_off")
            ):
                messages.append((abs_tick, track_index, msg_type, channel, value))
    messages.sort(key=lambda item: item[0])

    events = []
    tempo = 500000
    last_tick = 0
    seconds = 0.0
    for tick, track_index, msg_type, channel, value in messages:
        seconds += (tick - last_tick) * (tempo / 1_000_000) / ticks_per_beat
        last_tick = tick
        if msg_type == "set_tempo":
            tempo = value
        else:
            key = (track_index, channel, value)
            events.append((seconds, roles[track_index], key, msg_type == "note_on"))
    midi_length = seconds

    active = [set() for _ in range(CHANNELS)]
    prev_notes = [0] * CHANNELS
    notes = bytearray()
    cursor = 0
    # A light off-beat hat under the source's 138 BPM rhythm.
    eighth_beat = 30 / 138
    last_eighth = -1
    for tick in range(frames * TICKS_PER_FRAME):
        sample_time = tick / TICKS_PER_SECOND + offset
        retriggered = [False] * CHANNELS
        drum_hit = [False] * CHANNELS
        while cursor < len(events) and events[cursor][0] <= sample_time:
            event_time, voice, key, on = events[cursor]
            if voice == 3:
                if on:
                    drum_note = key[2]
                    drum = 0 if drum_note in (35, 36) else 1 if drum_note in (37, 38, 40) else 2
                    drum_hit[drum] = True
            elif on:
                active[voice].add(key)
                retriggered[voice] = True
            else:
                active[voice].discard(key)
            cursor += 1
        lead = max((note - 12 for _, _, note in active[0]), default=0)
        bass = min((note for _, _, note in active[1]), default=0)
        harmony = max(
            (note + 12 for track, _, note in active[2] if track in (7, 10, 11)),
            default=0,
        )
        if not harmony:
            harmony = max((note for _, _, note in active[2]), default=0)
        # Replace octave-doubled bass with a higher, quieter harmony.
        if bass and harmony == bass + 24:
            harmony += 7
        if 0 <= sample_time < midi_length:
            eighth = int(sample_time // eighth_beat)
            if eighth != last_eighth:
                last_eighth = eighth
                if eighth % 2:
                    drum_hit[2] = True
        for voice, raw_note in enumerate((lead, bass, harmony)):
            note = max(1, min(126, raw_note)) if raw_note > 0 else 0
            if note and note == prev_notes[voice] and retriggered[voice]:
                encoded = 0x7F
            else:
                encoded = note
                prev_notes[voice] = note
            notes.append(encoded | (0x80 if drum_hit[voice] else 0))
    return bytes(notes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--offset", type=float, default=0, help="MIDI start time in seconds")
    args = parser.parse_args()
    if not 1 <= args.frames <= 0xFFFF:
        parser.error("frames must be 1 to 65535")
    if args.midi.resolve() == args.output.resolve():
        parser.error("input and output must be different files")
    args.output.write_bytes(arrange(args.midi, args.frames, args.offset))


if __name__ == "__main__":
    main()
