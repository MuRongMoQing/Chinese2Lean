import Mathlib

theorem linear_deduction (x : ℝ) (y : ℝ) (h1 : x + y = 3) (h2 : x = 1) : y = 2 := by
  linarith
