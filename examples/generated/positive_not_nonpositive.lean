import Mathlib

theorem positive_not_nonpositive (x : ℝ) (hx : x > 0) : ¬(x ≤ 0) := by
  linarith
