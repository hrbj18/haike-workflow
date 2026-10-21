#!/usr/bin/env python3
"""Deterministic, sample-free commercial music and SFX for template 6.

Uses only NumPy and the repository's existing FFmpeg. No provider/network calls.
Creates 48 kHz stereo PCM24 WAVs, measured loudness, beat grids and provenance.
This is an asset composer; it neither reads nor changes voice/video sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

SR = 48000
ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "Haike_video"))
from lib.ffmpeg_locator import resolve_ffmpeg_pair

FFMPEG, FFPROBE = resolve_ffmpeg_pair()
SEED = 20261020
THEMES = {
    "main-118": {
        "bpm": 118, "seed": SEED + 118, "key": "D minor / F major",
        "title": "Copper Current / 铜流", "feel": "syncopated editorial electronic groove",
        "chords": [[50, 57, 60, 64, 65], [46, 53, 57, 60, 65],
                   [41, 53, 57, 60, 67], [48, 55, 60, 62, 64]],
        "bass": [38, 34, 29, 36], "kick": [0, 1.5, 2, 3.25],
        "swing": .055, "edge": 1.0, "master_lufs": -18,
    },
    "red-124": {
        "bpm": 124, "seed": SEED + 124, "key": "D minor",
        "title": "Make the Move / 即刻向前", "feel": "punchy industrial break-house",
        "chords": [[50, 57, 60, 64], [46, 53, 57, 60],
                   [48, 55, 60, 62], [45, 52, 55, 60]],
        "bass": [38, 34, 36, 33], "kick": [0, 1, 2, 2.75, 3.5],
        "swing": .025, "edge": 1.35, "master_lufs": -18,
    },
    "documentary-100": {
        "bpm": 100, "seed": SEED + 100, "key": "F major / D minor",
        "title": "Everyday Forward / 日常向前", "feel": "warm broken-beat Rhodes documentary groove",
        "chords": [[41, 53, 57, 60, 64], [45, 52, 55, 60, 64],
                   [48, 55, 60, 62, 64], [43, 50, 55, 59, 64]],
        "bass": [29, 33, 36, 31], "kick": [0, 1.75, 2.5],
        "swing": .11, "edge": .72, "master_lufs": -19,
    },
}
ROLES = ["drums", "bass", "harmony", "motif"]


def db(value):
    return 10 ** (value / 20)


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def clock(duration):
    return np.arange(max(1, round(duration * SR)), dtype=np.float64) / SR


def fade(signal, attack=.003, release=.025):
    result = np.asarray(signal, dtype=np.float64).copy()
    count = len(result)
    na = min(round(attack * SR), count)
    nr = min(round(release * SR), max(0, count - na))
    if na:
        ramp = np.sin(np.linspace(0, np.pi / 2, na)) ** 2
        result[:na] *= ramp if result.ndim == 1 else ramp[:, None]
    if nr:
        ramp = np.cos(np.linspace(0, np.pi / 2, nr)) ** 2
        result[-nr:] *= ramp if result.ndim == 1 else ramp[:, None]
    return result


def band(signal, low=0, high=20000, slope=4):
    """Smooth FFT shelving, rendered with padding to avoid circular ringing."""
    n = len(signal)
    size = 1 << (n + 2048 - 1).bit_length()
    freq = np.fft.rfftfreq(size, 1 / SR)
    response = 1 / np.sqrt(1 + (freq / max(high, 1)) ** (2 * slope))
    if low:
        response *= 1 / np.sqrt(1 + (low / np.maximum(freq, .001)) ** (2 * slope))
    if signal.ndim == 1:
        return np.fft.irfft(np.fft.rfft(signal, n=size) * response, n=size)[:n]
    return np.column_stack([band(signal[:, c], low, high, slope) for c in range(signal.shape[1])])


def stereo(signal, pan=0):
    if signal.ndim == 2:
        return signal
    angle = (max(-1, min(1, pan)) + 1) * np.pi / 4
    return np.column_stack((signal * np.cos(angle), signal * np.sin(angle)))


def add(target, signal, time, gain=1, pan=0):
    start = round(time * SR)
    signal = stereo(signal, pan)
    source_start = max(0, -start)
    start = max(0, start)
    end = min(len(target), start + len(signal) - source_start)
    if end > start:
        target[start:end] += signal[source_start:source_start + end - start] * gain


def saturation(signal, drive=1.5):
    return np.tanh(signal * drive) / drive


def kick(edge=1):
    t = clock(.37)
    frequency = 49 + 115 * np.exp(-t * 34)
    phase = np.cumsum(frequency) * 2 * np.pi / SR
    fundamental = np.sin(phase) * np.exp(-t * 18)
    body = (.32 * np.sin(phase * 2.01) + .13 * np.sin(phase * 3.0)) * np.exp(-t * 30)
    rng = np.random.default_rng(SEED + 1)
    click = band(rng.standard_normal(len(t)), 1500, 7000) * np.exp(-t * 280) * .13
    return fade(saturation(fundamental + body * edge + click, 1.7), .0004, .025)


def snare(edge=1):
    t = clock(.27)
    rng = np.random.default_rng(SEED + 2)
    noise = band(rng.standard_normal(len(t)), 950, 8200)
    env = np.exp(-t * 26)
    clap = np.zeros(len(t))
    for delay, amp in [(0, .38), (.011, .5), (.024, .48)]:
        dt = np.maximum(0, t - delay)
        clap += amp * np.exp(-dt * 58) * (t >= delay)
    body = np.sin(2 * np.pi * 185 * t + 1.3 * np.exp(-t * 36)) * np.exp(-t * 36) * .3
    return fade(saturation(noise * (env * .25 + clap * .55) * edge + body, 1.4), .0008, .025)


def hat(opened=False):
    duration = .22 if opened else .09
    t = clock(duration)
    rng = np.random.default_rng(SEED + 3 + int(opened))
    noise = band(rng.standard_normal(len(t)), 6200, 12500)
    metal = sum(np.sin(2 * np.pi * f * t) for f in [6701, 8209, 10313]) / 6
    env = np.exp(-t * (25 if opened else 66))
    return fade((noise * .6 + metal * .16) * env, .001, .02)


def shaker():
    t = clock(.14)
    rng = np.random.default_rng(SEED + 5)
    noise = band(rng.standard_normal(len(t)), 3700, 10400)
    env = (1 - np.exp(-t * 600)) * np.exp(-t * 46)
    return fade(noise * env * .38, .001, .015)


def wood_tick():
    t = clock(.13)
    rng = np.random.default_rng(SEED + 6)
    wood = np.sin(2 * np.pi * 790 * t + 2.6 * np.sin(2 * np.pi * 1210 * t) * np.exp(-t * 120))
    wood += .42 * np.sin(2 * np.pi * 1550 * t)
    noise = band(rng.standard_normal(len(t)), 1700, 6500) * np.exp(-t * 170) * .16
    return fade(wood * np.exp(-t * 81) * .38 + noise, .0005, .012)


def bass_note(midi, duration, edge=1):
    t = clock(duration + .075)
    f = hz(midi)
    phase = 2 * np.pi * f * t
    tone = np.sin(phase)
    for h in range(2, 11):
        tone += (1 / h ** 1.65) * np.sin(h * phase + .05 * h) * np.exp(-t * h * 1.6)
    tone += .18 * np.sin(phase / 2) if midi >= 36 else 0
    env = (1 - np.exp(-t * 420)) * np.exp(-t * (2.4 if duration > .25 else 4.0))
    gate = np.clip((duration + .075 - t) / .075, 0, 1)
    return fade(saturation(tone * env * gate, 1.5 * edge), .002, .025)


def keys_note(midi, duration, warmth=1):
    t = clock(duration + .4)
    f = hz(midi)
    # A tine-like two-operator FM voice, with mechanical transient and a soft body.
    index = 1.9 * np.exp(-t * 8) + .36
    phase = 2 * np.pi * f * t
    tone = np.sin(phase + index * np.sin(phase * 2.002))
    tone += .18 * np.sin(phase * 1.003) + .1 * np.sin(phase * .997 + .2)
    tone += .08 * np.sin(phase * 3) * np.exp(-t * 16)
    env = (1 - np.exp(-t * 460)) * np.exp(-t * (1.8 / warmth))
    env *= np.clip((duration + .4 - t) / .4, 0, 1)
    return fade(tone * env * .32, .003, .08)


def pad_chord(notes, duration):
    t = clock(duration + .65)
    left = np.zeros(len(t))
    right = np.zeros(len(t))
    for i, midi in enumerate(notes):
        f = hz(midi)
        for harmonic, amp in [(1, 1), (2, .23), (3, .08), (4, .035)]:
            left += amp * np.sin(2 * np.pi * f * harmonic * .9987 * t + i * .64)
            right += amp * np.sin(2 * np.pi * f * harmonic * 1.0011 * t + i * .67 + .18)
    env = np.sin(np.pi / 2 * np.clip(t / .35, 0, 1)) ** 2
    env *= np.clip((duration + .65 - t) / .65, 0, 1)
    env *= .88 + .12 * np.sin(2 * np.pi * .25 * t)
    return np.column_stack((left, right)) * env[:, None] * .065


def pluck(midi, duration=.5, edge=1):
    t = clock(duration)
    f = hz(midi)
    phase = 2 * np.pi * f * t
    tone = np.sin(phase + (.9 * edge) * np.sin(phase * 2.01) * np.exp(-t * 14))
    tone += .18 * np.sin(phase * 3.002) * np.exp(-t * 12)
    env = (1 - np.exp(-t * 900)) * np.exp(-t * 9)
    return fade(tone * env * .35, .002, .07)


def spatial_bus(signal, amount=.13):
    # Short early reflections, filtered alternating taps: dry-center voice remains uncluttered.
    wet = np.zeros_like(signal)
    mono = signal.mean(axis=1)
    filtered = band(mono, 350, 4600)
    for i, (delay, level) in enumerate([(.037, .32), (.071, .26), (.113, .20), (.173, .14), (.251, .09)]):
        shift = round(SR * delay)
        if shift < len(signal):
            wet[shift:, i % 2] += filtered[:-shift] * level
            wet[shift:, 1 - i % 2] += filtered[:-shift] * level * .45
    return signal + wet * amount


def arrangement(bar):
    if bar < 2:
        return "intro", .65, .66, .52, .32
    if bar < 8:
        return "groove_a", 1, 1, .8, .52
    if bar < 12:
        return "expansion", 1.06, 1, 1, .88
    if bar < 14:
        return "break", .32, .58, .96, .45
    if bar < 18:
        return "return", 1.1, 1.03, 1, 1
    return "outro", .78, .82, .74, .5


def compose_theme(theme_id):
    cfg = THEMES[theme_id]
    beat = 60 / cfg["bpm"]
    length = round(20 * 4 * beat * SR)
    stems = {r: np.zeros((length, 2), dtype=np.float64) for r in ROLES}
    rng = np.random.default_rng(cfg["seed"])
    doc = theme_id.startswith("documentary")
    red = theme_id.startswith("red")
    edge = cfg["edge"]
    instruments = {"kick": kick(edge), "snare": snare(edge), "hat": hat(),
                   "open": hat(True), "shaker": shaker(), "tick": wood_tick()}
    events = []

    def hit(name, bar, position, gain, pan=0, jitter=False):
        at = (bar * 4 + position) * beat
        if jitter and at > .01:
            at += rng.uniform(-.0025, .0025)
        add(stems["drums"], instruments[name], at, gain, pan)
        events.append({"instrument": name, "time": round(at, 6), "bar": bar + 1, "beat": position + 1})

    for bar in range(20):
        section, dg, bg, hg, mg = arrangement(bar)
        chord_index = (bar // 2) % 4
        chord = cfg["chords"][chord_index]
        root = cfg["bass"][chord_index]
        start = bar * 4 * beat
        # A musical two-bar harmonic rhythm, not a repeating single-tone bed.
        if bar % 2 == 0:
            add(stems["harmony"], pad_chord([m + 12 if m < 48 else m for m in chord], 8 * beat), start, .55 * hg)

        kicks = cfg["kick"]
        if section == "break":
            kicks = [0] if bar == 12 else [2.5]
        if section == "intro" and bar == 0:
            kicks = [0, 2]
        for p in kicks:
            hit("kick", bar, p, (.78 if doc else .92) * dg * rng.uniform(.94, 1.03))
        if section != "break":
            for p in [1, 3]:
                hit("tick" if doc else "snare", bar, p, (.52 if doc else .55) * dg, -.08 if p == 1 else .08, True)
            if red and bar % 4 == 3:
                for p, v in [(3.5, .19), (3.75, .26)]:
                    hit("snare", bar, p, v * dg, .08, True)
        else:
            hit("tick", bar, 3, .22, -.1)

        subdivision = .5 if (doc or section == "intro" or section == "break") else .25
        for i in range(round(4 / subdivision)):
            p = i * subdivision
            if section == "break" and i % 2 == 1:
                continue
            if subdivision == .25 and i % 2 == 1 and (i + bar) % 3 == 0:
                continue
            swing = cfg["swing"] if i % 2 else 0
            v = (.15 if i % 2 else .23) * dg * rng.uniform(.8, 1.06)
            hit("shaker" if doc else "hat", bar, p + swing, v, -.32 if i % 2 else .3, True)
        if not doc and section not in ["intro", "break"]:
            hit("open", bar, 2.5 + cfg["swing"], .13 * dg, .25)
        if doc and bar % 2 == 1:
            hit("tick", bar, 3.75, .17 * dg, .28, True)
        if bar in [7, 11, 17]:
            for p, gain in [(3.25, .12), (3.5, .17), (3.75, .25)]:
                hit("tick", bar, p, gain, .18)

        if doc:
            bass_pattern = [(0, 0, 1.18), (1.75, 7, .45), (2.5, 0, .82), (3.5, 12, .24)]
        elif red:
            bass_pattern = [(0, 0, .45), (.75, 0, .34), (1.5, 12, .3), (2, 0, .45), (2.75, 7, .3), (3.5, 0, .32)]
        else:
            bass_pattern = [(0, 0, .72), (1.25, 7, .28), (1.75, 12, .28), (2.5, 0, .62), (3.5, 7, .32)]
        if section == "break":
            bass_pattern = bass_pattern[:1]
        for p, interval, length_beats in bass_pattern:
            add(stems["bass"], bass_note(root + interval, length_beats * beat, edge), start + p * beat, .52 * bg)

        key_positions = [(.08, .95), (1.75, .55), (3.25, .55)] if doc else [(.0, .72), (1.5, .42), (2.75, .5)]
        if section == "break":
            key_positions = [(.0, 1.3)]
        for p, dur in key_positions:
            for j, note in enumerate(chord[1:]):
                add(stems["harmony"], keys_note(note + 12, dur * beat, 1.35 if doc else .9),
                    start + p * beat + j * .006, .24 * hg / math.sqrt(len(chord) - 1), (j - 1.5) * .16)

        # Answering motifs alternate in two-bar phrases; leave narration space.
        motif_positions = [(2.5, 0), (3.25, 2)] if bar % 2 == 0 else [(.75, 1), (2.75, 3), (3.5, 2)]
        if doc:
            motif_positions = [(3.25, 1)] if bar % 2 == 0 else [(1.75, 2)]
        if section == "intro" and bar == 0:
            motif_positions = [(3.5, 2)]
        if section == "break":
            motif_positions = [(2.75, 1)]
        for j, (p, note_index) in enumerate(motif_positions):
            note = chord[1 + note_index % (len(chord) - 1)] + (12 if doc else 24)
            add(stems["motif"], pluck(note, .65 if doc else .49, edge), start + p * beat,
                .34 * mg * rng.uniform(.88, 1.04), -.25 if j % 2 else .25)

    # Gentle energy dip on harmony/motif at each kick creates groove without pumping VO.
    pulse = np.ones(length)
    for event in events:
        if event["instrument"] != "kick":
            continue
        offset = round(event["time"] * SR)
        n = min(round(.24 * SR), length - offset)
        if n > 0:
            pulse[offset:offset+n] *= 1 - .18 * np.exp(-np.arange(n) / SR * 16)
    stems["harmony"] *= pulse[:, None]
    stems["motif"] *= pulse[:, None]
    stems["harmony"] = spatial_bus(band(stems["harmony"], 115, 6100), .38)
    stems["motif"] = spatial_bus(band(stems["motif"], 480 if not doc else 260, 5700), .55)
    stems["drums"] = band(stems["drums"], 27, 14500)
    stems["bass"] = band(stems["bass"], 30, 2200)
    # Controlled sample-level soft colour, not clipping; all stem fades are phase coherent.
    for role in ROLES:
        stems[role] = np.column_stack([fade(stems[role][:, c], .006, .55) for c in range(2)])
        stems[role] -= stems[role].mean(axis=0)
    return stems, events


def meter_array(signal, log_path):
    command = [FFMPEG, "-hide_banner", "-nostdin", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "pipe:0",
               "-af", "loudnorm=I=-18:TP=-2:LRA=11:print_format=json", "-f", "null", "-"]
    result = subprocess.run(command, input=np.asarray(signal, dtype="<f4").tobytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr = result.stderr.decode("utf-8", errors="replace")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(stderr[-3000:])
    match = re.findall(r'\{\s*"input_i".*?\}', stderr, re.S)
    if not match:
        raise RuntimeError("FFmpeg did not return integrated/truepeak metrics")
    values = json.loads(match[-1])
    return {"integrated_lufs": float(values["input_i"]), "true_peak_dbtp": float(values["input_tp"]),
            "lra_lu": float(values["input_lra"]), "threshold_lufs": float(values["input_thresh"])}


def write_pcm24(path, signal):
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [FFMPEG, "-y", "-hide_banner", "-nostdin", "-f", "f32le", "-ar", str(SR), "-ac", "2",
               "-i", "pipe:0", "-map_metadata", "-1", "-c:a", "pcm_s24le", str(path)]
    result = subprocess.run(command, input=np.asarray(signal, dtype="<f4").tobytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-3000:])


def file_metrics(path):
    result = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, check=True)
    return json.loads(result.stdout)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_metrics(metrics):
    return {key: value if math.isfinite(value) else None for key, value in metrics.items()}


def describe_asset(asset_id, path, signal, metrics, **extra):
    peak = float(np.max(np.abs(signal)))
    rms = np.sqrt(np.mean(signal ** 2, axis=0))
    correlation = float(np.corrcoef(signal[:, 0], signal[:, 1])[0, 1])
    return {
        "asset_id": asset_id, "path": str(path.resolve()), "sha256": hash_file(path), "bytes": path.stat().st_size,
        "duration_seconds": len(signal) / SR, "sample_count": len(signal), "sample_rate": SR,
        "channels": 2, "codec": "pcm_s24le", "bits_per_sample": 24,
        **safe_metrics(metrics), "sample_peak_dbfs": round(20 * math.log10(max(peak, 1e-15)), 5),
        "rms_dbfs_channels": [round(20 * math.log10(max(float(r), 1e-15)), 5) for r in rms],
        "stereo_correlation": round(correlation, 5), "finite": bool(np.isfinite(signal).all()),
        "clipped_samples": int(np.count_nonzero(np.abs(signal) >= 1)), **extra,
    }


def create_theme(theme_id):
    cfg = THEMES[theme_id]
    print("COMPOSE " + theme_id, flush=True)
    stems, events = compose_theme(theme_id)
    # Role-dependent linear LUFS alignment then a single common bus gain preserves reconstruction.
    targets = {"drums": (-22.5, -5.5), "bass": (-25, -7), "harmony": (-26, -8), "motif": (-29, -9)}
    pre_align = {}
    for role in ROLES:
        meter = meter_array(stems[role], OUT / "analysis" / theme_id / (role + "-raw.log"))
        target_i, cap = targets[role]
        gain_db = min(target_i - meter["integrated_lufs"], cap - meter["true_peak_dbtp"])
        stems[role] *= db(gain_db)
        pre_align[role] = {"nominal_lufs": target_i, "truepeak_cap": cap, "gain_db": gain_db, "raw_metrics": safe_metrics(meter)}
    mix = sum(stems.values())
    initial = meter_array(mix, OUT / "analysis" / theme_id / "mix-pre-master.log")
    desired_gain = cfg["master_lufs"] - initial["integrated_lufs"]
    allowed_gain = -2.2 - initial["true_peak_dbtp"]
    # Enough headroom is expected; avoid a nonlinear master or VO-like loudness war.
    common_gain = min(desired_gain, allowed_gain)
    for role in ROLES:
        stems[role] *= db(common_gain)
    mix = sum(stems.values())
    assets = []
    for role, signal in [*stems.items(), ("master", mix)]:
        path = OUT / "music" / theme_id / (role + ".wav")
        write_pcm24(path, signal)
        metric = meter_array(signal, OUT / "analysis" / theme_id / (role + "-final.log"))
        assets.append(describe_asset(theme_id + ":" + role, path, signal, metric,
            role=role, theme_id=theme_id, bpm=cfg["bpm"], key=cfg["key"], seed=cfg["seed"],
            nominal_master_lufs=cfg["master_lufs"], master_truepeak_cap_dbtp=-2.2, common_master_gain_db=round(common_gain, 6),
            normalization="linear role alignment + common linear master gain; no limiter/compressor",
            role_pre_alignment=pre_align.get(role)))
        print(f"  {role}: {metric['integrated_lufs']:.2f} LUFS / {metric['true_peak_dbtp']:.2f} dBTP", flush=True)
    beat = 60 / cfg["bpm"]
    sections = [{"name": name, "start_bar": a+1, "end_bar_exclusive": b+1,
                 "start_seconds": a*4*beat, "end_seconds": b*4*beat}
                for name, a, b in [("intro",0,2),("groove_a",2,8),("expansion",8,12),("break",12,14),("return",14,18),("outro",18,20)]]
    save_json(OUT / "music" / theme_id / "beat-grid.json", {
        "theme_id": theme_id, "bpm": cfg["bpm"], "meter": "4/4", "first_downbeat_seconds": 0,
        "beat_seconds": beat, "bar_seconds": beat*4, "bar_count": 20,
        "sections": sections,
        "beats": [{"index": i, "bar": i//4+1, "beat_in_bar": i%4+1, "seconds": round(i*beat, 9)} for i in range(80)],
        "note": "Music grid only. Preserve real narration word clocks; do not quantize speech or all SFX to this grid.",
        "percussion_events": events,
    })
    save_json(OUT / "music" / theme_id / "arrangement.json", {**cfg, "sections": sections,
        "stems_sum_to_master": True, "common_master_gain_db": common_gain,
        "role_pre_alignment": pre_align, "master_before_gain": safe_metrics(initial),
        "actual_master_target_lufs": round(initial["integrated_lufs"] + common_gain, 3),
        "reconstruction_tolerance": "24-bit export quantization only (sum stems without normalization)",
        "external_samples": [], "lyrics": False})
    return assets


def impact():
    t = clock(.73)
    rng = np.random.default_rng(SEED + 27)
    f = 62 + 190 * np.exp(-t * 31)
    phase = np.cumsum(f) * 2 * np.pi / SR
    low = np.sin(phase) * np.exp(-t * 12)
    mid = (.5 * np.sin(phase * 2.01) + .3 * np.sin(phase * 3.02) + .13 * np.sin(phase * 5.01)) * np.exp(-t * 21)
    metal = (np.sin(2*np.pi*440*t) + .45*np.sin(2*np.pi*687*t)) * np.exp(-t*29) * .11
    attack = band(rng.standard_normal(len(t)), 850, 6800) * np.exp(-t * 112) * .2
    signal = fade(saturation(low + mid + metal + attack, 2), .0003, .06)
    return spatial_bus(stereo(signal), .14)


def whoosh():
    t = clock(.72)
    rng = np.random.default_rng(SEED + 28)
    noise = rng.standard_normal(len(t))
    low = band(noise, 180, 850)
    mid = band(noise, 550, 2600)
    air = band(noise, 1800, 9000)
    position = t / t[-1]
    flow = low * (1-position) + mid * np.sin(np.pi*position) * .8 + air * position * .5
    env = np.sin(np.pi * np.clip(position ** 1.3,0,1)) ** 1.9
    flow *= env
    pan = -.55 + 1.1 * position
    signal = np.column_stack((flow*np.sqrt((1-pan)/2), flow*np.sqrt((1+pan)/2)))
    return fade(signal, .025, .09)


def riser():
    t = clock(1.12)
    rng = np.random.default_rng(SEED + 29)
    noise = band(rng.standard_normal(len(t)), 450, 6500)
    p = t/t[-1]
    phase = 2*np.pi*(110*t + 380*t*t)
    tone = (np.sin(phase) + .22*np.sin(phase*2.03)) * .22
    pulse = .72 + .28*np.sin(2*np.pi*(6*t+3*t*t))
    env = np.sin(np.pi/2*p) ** 2 * np.clip((1-p)/.12,0,1)
    return fade(stereo((noise*.33+tone)*pulse*env), .05, .04)


def create_sfx():
    dong = spatial_bus(stereo(kick(1.3)), .12)
    full = impact()
    tick = stereo(wood_tick())
    triple = np.zeros((round(1.05*SR),2))
    for at, level in [(0,.72),(.14,.84),(.29,1.0)]:
        add(triple, full, at, level)
    light = np.zeros((round(.53*SR),2))
    for i, at in enumerate([0,.14,.29]):
        add(light, tick, at, .72+i*.11, -.2+i*.2)
    values = {"dong": (dong, .0, "short low-mid punch; use at opening or large figure"),
              "impact": (full, .0, "richer body + metallic mid transient; major semantic change"),
              "whoosh": (whoosh(), .43, "sweeping short transition; visualSyncMs identifies crest, not onset"),
              "tick": (tick, .0, "brief wooden mid tap; list or detail"),
              "triple-impact": (triple, .0, "three attacks at 0 / 140 / 290 ms, optional opening or offer only"),
              "light-triple": (light, .0, "three light taps at 0 / 140 / 290 ms, optional AI list"),
              "riser": (riser(), 1.0, "short phrase transition; use sparingly, crest before cut")}
    assets=[]
    for asset_id, (signal, sync, purpose) in values.items():
        print("SFX " + asset_id, flush=True)
        metric = meter_array(signal, OUT / "analysis" / "sfx" / (asset_id+"-raw.log"))
        gain = -3.2 - metric["true_peak_dbtp"]
        signal *= db(gain)
        path = OUT / "sfx" / (asset_id+".wav")
        write_pcm24(path, signal)
        metric = meter_array(signal, OUT / "analysis" / "sfx" / (asset_id+"-final.log"))
        sample_env = np.max(np.abs(signal),axis=1)
        peak_sample = int(np.argmax(sample_env))
        onset = int(np.flatnonzero(sample_env > np.max(sample_env)*.03)[0])
        metrics = describe_asset(asset_id,path,signal,metric,role="sfx",purpose=purpose,
            target_true_peak_dbtp=-3.2, normalization="linear true-peak alignment; not LUFS forced for transient",
            transientOffsetMs=round(onset/SR*1000,3), peak_offset_ms=round(peak_sample/SR*1000,3),
            visualSyncMs=round(sync*1000,3), attack_times_ms=[0,140,290] if "triple" in asset_id else [0],
            loudness_note="Integrated LUFS is descriptive only for short effects; do not equalize short effects by LUFS.")
        assets.append(metrics)
        print(f"  {metric['integrated_lufs']:.2f} LUFS / {metric['true_peak_dbtp']:.2f} dBTP; onset {metrics['transientOffsetMs']} ms", flush=True)
    return assets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=list(THEMES), help="regenerate one theme, updating this pack manifest")
    parser.add_argument("--sfx-only", action="store_true")
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    manifest_path=OUT/"manifest.json"
    previous=json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    assets=previous.get("assets",[]) if args.theme or args.sfx_only else []
    if not args.sfx_only:
        for theme_id in ([args.theme] if args.theme else THEMES):
            assets=[a for a in assets if a.get("theme_id") != theme_id]
            assets.extend(create_theme(theme_id))
    if not args.theme:
        assets=[a for a in assets if a.get("role") != "sfx"]
        assets.extend(create_sfx())
    manifest={
        "schema":"haike.original_sound_pack.v1", "pack_id":"template6-original-electronic-20261020",
        "created_utc":datetime.now(timezone.utc).isoformat(), "generator":str(Path(__file__).resolve()),
        "generator_sha256":hash_file(Path(__file__)), "seed":SEED,
        "software":{"numpy":np.__version__,"ffmpeg":FFMPEG,"ffprobe":FFPROBE},
        "generation_method":"local deterministic procedural composition; additive/FM/subtractive-noise DSP",
        "cloud_calls":0,"downloads":0,"paid_calls":0,"external_samples":[],"voice_or_video_sources_read":[],
        "target_master_lufs_by_theme":{key:value["master_lufs"] for key,value in THEMES.items()},"target_master_truepeak_max_dbtp":-2.2,
        "assets":assets,
        "scope":"Reusable assets only. No complete-video mix, subjective listening approval, publication or lip-sync verification.",
    }
    save_json(manifest_path,manifest)
    checks={
        "asset_count":len(assets),"expected_count":22,
        "all_finite":all(a["finite"] for a in assets),
        "all_without_clipped_samples":all(a["clipped_samples"]==0 for a in assets),
        "all_48k_stereo_pcm24":all(a["sample_rate"]==48000 and a["channels"]==2 and a["bits_per_sample"]==24 for a in assets),
        "master_loudness_within_point2":all(abs(a["integrated_lufs"]-a["nominal_master_lufs"])<=.2 for a in assets if a["role"]=="master"),
        "master_truepeak_below_minus2":all(a["true_peak_dbtp"]<=-2 for a in assets if a["role"]=="master"),
        "sfx_truepeak_below_minus3":all(a["true_peak_dbtp"]<=-3 for a in assets if a["role"]=="sfx"),
        "all_hashes_match":all(hash_file(Path(a["path"]))==a["sha256"] for a in assets),
        "subjective_listening_approved":False,
    }
    save_json(OUT/"asset-checks.json",checks)
    print(json.dumps(checks,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
