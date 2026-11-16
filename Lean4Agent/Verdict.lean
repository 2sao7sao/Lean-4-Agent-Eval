import Std

namespace Lean4Agent

/-- Results of mandatory checks. Evidence extraction is outside this model. -/
inductive Verdict where
  | pass | fail | unknown | error
  deriving DecidableEq, Repr

/-- Known failure dominates; otherwise error, unknown, then pass. -/
def combine (a b : Verdict) : Verdict :=
  match a, b with
  | .fail, _ | _, .fail => .fail
  | .error, _ | _, .error => .error
  | .unknown, _ | _, .unknown => .unknown
  | .pass, .pass => .pass

def foldVerdicts : List Verdict → Verdict
  | [] => .pass
  | v :: vs => combine v (foldVerdicts vs)

/-- Empty requirements do not certify task success. -/
def aggregate : List Verdict → Verdict
  | [] => .unknown
  | v :: vs => combine v (foldVerdicts vs)

theorem combine_pass_iff (a b : Verdict) :
    combine a b = .pass ↔ a = .pass ∧ b = .pass := by
  cases a <;> cases b <;> simp [combine]

theorem fold_pass_iff (vs : List Verdict) :
    foldVerdicts vs = .pass ↔ ∀ v ∈ vs, v = .pass := by
  induction vs with
  | nil => simp [foldVerdicts]
  | cons v vs ih => simp [foldVerdicts, combine_pass_iff, ih]

/-- Pass exactly when there is at least one check and every check passes. -/
theorem aggregate_pass_iff (vs : List Verdict) :
    aggregate vs = .pass ↔ vs ≠ [] ∧ ∀ v ∈ vs, v = .pass := by
  cases vs with
  | nil => simp [aggregate]
  | cons v vs => simp [aggregate, combine_pass_iff, fold_pass_iff]

theorem empty_is_unknown : aggregate [] = .unknown := by rfl

theorem fold_fail (vs : List Verdict) (h : Verdict.fail ∈ vs) :
    foldVerdicts vs = .fail := by
  induction vs with
  | nil => simp at h
  | cons v vs ih =>
    rcases List.mem_cons.mp h with hv | ht
    · subst v; rfl
    · cases v <;> simp [foldVerdicts, ih ht, combine]

theorem known_failure_dominates (vs : List Verdict) (h : Verdict.fail ∈ vs) :
    aggregate vs = .fail := by
  cases vs with
  | nil => simp at h
  | cons v vs => simpa [aggregate, foldVerdicts] using fold_fail (v :: vs) h

theorem nonpass_blocks (vs : List Verdict) (v : Verdict)
    (present : v ∈ vs) (notPass : v ≠ .pass) : aggregate vs ≠ .pass := by
  intro accepted
  exact notPass (((aggregate_pass_iff vs).mp accepted).2 v present)

theorem unknown_blocks (vs : List Verdict) (present : Verdict.unknown ∈ vs) :
    aggregate vs ≠ .pass :=
  nonpass_blocks vs .unknown present (by decide)

theorem error_blocks (vs : List Verdict) (present : Verdict.error ∈ vs) :
    aggregate vs ≠ .pass :=
  nonpass_blocks vs .error present (by decide)

/-- The contract, not the submitted results, determines which checks are needed.
    Receipt parsing and the correctness of each receipt remain outside the model. -/
def evaluateRequired (required : List Nat) (receipts : Nat → Option Verdict) : Verdict :=
  aggregate (required.map fun id => (receipts id).getD .unknown)

theorem missing_required_blocks (required : List Nat) (receipts : Nat → Option Verdict)
    (id : Nat) (needed : id ∈ required) (missing : receipts id = none) :
    evaluateRequired required receipts ≠ .pass := by
  unfold evaluateRequired
  apply unknown_blocks
  apply List.mem_map.mpr
  exact ⟨id, needed, by simp [missing]⟩

theorem empty_contract_is_unknown (receipts : Nat → Option Verdict) :
    evaluateRequired [] receipts = .unknown := by rfl

example : aggregate [.pass, .unknown] = .unknown := by decide
example : aggregate [.error, .fail] = .fail := by decide
example : aggregate [.pass, .pass] = .pass := by decide
example : evaluateRequired [1, 2] (fun id => if id = 1 then some .pass else none)
    = .unknown := by decide

end Lean4Agent
