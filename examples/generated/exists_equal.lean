import Mathlib

theorem exists_equal (x : ℝ) : ∃ y : ℝ, y = x := by
  exact ⟨x, rfl⟩
