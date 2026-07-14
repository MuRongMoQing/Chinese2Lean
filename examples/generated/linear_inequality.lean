import Mathlib

theorem linear_inequality (x : ℝ) (hx : x > 2) : 2 * x + 1 > 5 := by
  linarith
