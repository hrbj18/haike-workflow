from decimal import Decimal
import pytest
from backlot.avatar_one_stop_policy import SPEECH_RATE_RULE, calibrate, effective_characters, validate_rate
from backlot.work_catalog import WorkError


def test_measured_rate_uses_source_multiplier_and_nearest_five_hundredths():
    assert effective_characters('你好，ＡＩ ２０２６！') == 8
    slow=calibrate('字'*40,10,target_cps=4.871709777149124)
    assert slow['rate']==1.2 and not slow['clamped']
    fast=calibrate('字'*55,10,target_cps=4.871709777149124)
    assert fast['rate']==.9
    assert calibrate('字'*40,10,target_cps=4.1)['rate']==1.05
    assert calibrate('字'*40,10,target_cps=4,sample_rate=1.15)['rate']==1.15
    assert calibrate('字'*40,10,target_cps=100)['clamped']
    for chars in range(1,300):
        result=calibrate('字'*chars,10,target_cps=4.87171)
        assert Decimal(str(result['rate'])) % Decimal('.05') == 0
        assert .5 <= result['rate'] <= 2


@pytest.mark.parametrize('seconds,target,rate',[(0,4,1),(-1,4,1),(float('nan'),4,1),(10,float('inf'),1),(10,4,True),(10,4,2.1)])
def test_invalid_measurements_do_not_produce_a_rate(seconds,target,rate):
    with pytest.raises(WorkError):calibrate('测试',seconds,target_cps=target,sample_rate=rate)


def test_explicit_rate_uses_exact_five_hundredths():
    assert validate_rate(1.15)==1.15
    for value in (True,1.13,0,2.05,float('nan')):
        with pytest.raises(WorkError):validate_rate(value)


def test_known_full_narration_selects_candidate_without_claiming_acceptance():
    result = calibrate('字' * 299, 66.442125, target_cps=4.9, sample_rate=.95)
    assert result['rate'] == 1.05
    assert result['raw_rate'] == pytest.approx(1.0344084, abs=.00001)
    assert result['measured_cps'] * 5 == pytest.approx(22.50078546)
    assert 'accepted' not in result


def test_current_tolerance_accepts_2508_and_rejects_the_reported_slow_and_fast_takes():
    band = SPEECH_RATE_RULE['characters_per_five_seconds']
    assert band == {'minimum': 23.5, 'maximum': 25.5, 'target': 24.5}
    assert band['minimum'] <= 299 / 59.617375 * 5 <= band['maximum']
    for observed in (22.5644908619, 27.1346203876):
        assert not band['minimum'] <= observed <= band['maximum']
