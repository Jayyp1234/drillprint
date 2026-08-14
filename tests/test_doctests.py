"""Spec §15 hard rule: every engine module carries doctest-style examples."""

import doctest

import engine.hashing
import engine.stft
import engine.types


def test_doctests_pass():
    for mod in (engine.types, engine.stft, engine.hashing):
        failures, tried = doctest.testmod(mod).failed, doctest.testmod(mod).attempted
        assert tried > 0, f"{mod.__name__} has no doctests"
        assert failures == 0, f"{mod.__name__} doctest failures"
