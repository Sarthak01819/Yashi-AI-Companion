from core.voice.stt import is_wake


def test_wake_threshold():
    assert is_wake(0.011, "Yashi")
    assert is_wake(0.045, "What time is it?")      # name lost from the text, heard in the audio
    assert not is_wake(0.002, "Yoshi")


def test_soundalike_needs_strong_evidence():
    assert not is_wake(0.034, "Yes, she did")
    assert is_wake(0.3, "Yes she")
