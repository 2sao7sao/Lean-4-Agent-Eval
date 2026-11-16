import Std

/-
Numerical specification and proofs for the teaching project.
Observed verification status is recorded in evidence/formal_verification.json.

Scope: finite lists of mathematical integer amounts (cents).
Excluded: CSV parsing, currency conversion, business scope, source authenticity,
Python equivalence, deployment behavior, PPT content and statistical reliability.

Run scripts/check_proofs.py to build, audit axioms, and exercise negative controls.
-/

namespace Lean4Agent

def total : List Int → Int
  | [] => 0
  | x :: xs => x + total xs

def checkTotal (rows : List Int) (claimed : Int) : Bool :=
  decide (claimed = total rows)

-- If this checker accepts, its numerical specification holds.
theorem checkTotal_sound (rows : List Int) (claimed : Int)
    (accepted : checkTotal rows claimed = true) : claimed = total rows := by
  simpa [checkTotal] using accepted

-- For this decidable numerical specification the checker also accepts all
-- correct claims. This does not generalize to arbitrary office-task quality.
theorem checkTotal_complete (rows : List Int) (claimed : Int)
    (correct : claimed = total rows) : checkTotal rows claimed = true := by
  simp [checkTotal, correct]

-- A reusable algebraic property, applying to all finite integer lists.
theorem total_append (xs ys : List Int) :
    total (xs ++ ys) = total xs + total ys := by
  induction xs with
  | nil => simp [total]
  | cons x xs ih => simp [total, ih, Int.add_assoc]

-- Concrete acceptance and rejection examples, not a statistical evaluation.
example : checkTotal [10000, 20000, -2000] 28000 = true := by decide
example : checkTotal [10000, 20000, -2000] 30000 = false := by decide

end Lean4Agent
