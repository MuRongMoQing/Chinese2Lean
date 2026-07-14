import Mathlib

theorem add_pos_of_pos (x : ℝ) (y : ℝ) (hx : x > 0) (hy : y > 0) : x + y > 0 := by
  linarith
