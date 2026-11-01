"""Measured temporal evidence must not turn into invented semantic certainty."""
from pathlib import Path
import subprocess

import numpy as np
import pytest

from backlot import reference_motion as motion
from backlot import reference_understanding as ref
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def test_phrase_preserves_real_word_clock_and_sentence_fallback():
    rows = ref.transcript({'source_sha256': 'same', 'clock': 'measured-seconds', 'segments': [
        {'id': 'a', 'start': 1, 'end': 5, 'text': '看看 AI 工具', 'words': [
            {'start': 1, 'end': 2, 'text': '看看'}, {'start': 3.4, 'end': 4.1, 'text': 'AI'},
            {'start': 4.2, 'end': 5, 'text': '工具'}]},
        {'id': 'b', 'start': 7, 'end': 9, 'text': '看看AI工具'}]}, 'same', 10)
    matches = motion.phrase_ranges(rows, 'ＡＩ，工具', 10, padding=0)
    assert matches[0]['start'] == 3.4 and matches[0]['end'] == 5
    assert matches[0]['word_ids'] == ['a:w2', 'a:w3']
    assert matches[1]['start'] == 7 and matches[1]['end'] == 9
    assert matches[1]['granularity'] == 'measured-sentence' and not matches[1]['word_ids']
    assert motion.phrase_ranges(rows, 'AI工具', 10, occurrence=2)[0]['start'] == 6.5
    with pytest.raises(ValueError, match='未找到'):
        motion.phrase_ranges(rows, '未说过的词', 10)
    with pytest.raises(ValueError, match='序号'):
        motion.phrase_ranges(rows, 'AI工具', 10, occurrence=3)


def test_local_activity_does_not_become_a_cut_or_bad_quality():
    first = np.zeros((40, 60, 3), dtype=np.uint8)
    second = first.copy()
    second[:10, :10] = 255
    quiet = motion.measurements(first, first)
    active = motion.measurements(first, second)
    assert quiet['mean_change'] == 0 and not quiet['cut_candidate']
    assert not active['cut_candidate']
    assert max(active['tiles'], key=lambda x: x['mean_change']) == active['tiles'][0]
    cut = motion.measurements(first, np.full_like(first, 255))
    assert cut['cut_candidate'] and cut['changed_fraction'] == 1
    assert 'quality' not in cut


def test_real_scan_keeps_source_pts_and_detects_a_transition(tmp_path):
    pair = resolve_ffmpeg_pair()
    if not pair:
        pytest.skip('FFmpeg/ffprobe unavailable')
    source = tmp_path/'source.mp4'
    subprocess.run([pair[0], '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
        'color=black:s=120x80:r=10:d=1', '-f', 'lavfi', '-i', 'color=white:s=120x80:r=10:d=1',
        '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0', '-c:v', 'libx264', str(source)], check=True)
    result = motion.scan(source, tmp_path/'scan', ffmpeg=pair[0], ffprobe=pair[1], every=.25, width=120)
    value = motion.load_scan(result['scan'])
    times = [r['at'] for r in value['frames']]
    assert all(abs(t*10-round(t*10)) < .001 for t in times)
    assert times[:3] == [0, .3, .6] # actual frames, not synthetic quarter-second timestamps
    assert any(r['motion'] and r['motion']['cut_candidate'] for r in value['frames'])
    assert result['review_status'] == 'pending' and result['production_ready'] is False
    assert motion.scan(source, tmp_path/'scan', ffmpeg=pair[0], ffprobe=pair[1], every=.25, width=120)['reused']
    Path(value['frames'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='图片已改变'):
        motion.load_scan(result['scan'])
