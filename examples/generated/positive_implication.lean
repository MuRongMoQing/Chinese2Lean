import Mathlib

theorem positive_implication (x : ℝ) : x > 0 → x + 1 > 0 := by
  intro h
  linarith
