import Mathlib

theorem conjunction_elimination (x : ℝ) (h1 : x > 0 ∧ x < 2) : x > 0 := by
  exact h1.1
