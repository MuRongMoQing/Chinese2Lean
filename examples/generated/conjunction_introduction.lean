import Mathlib

theorem conjunction_introduction (x : ℝ) (h1 : x > 0) (h2 : x < 2) : x > 0 ∧ x < 2 := by
  aesop
