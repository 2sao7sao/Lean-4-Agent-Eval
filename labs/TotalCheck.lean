-- Compatibility entry point for the first lesson.
-- From the project root: sh scripts/lean.sh env lean labs/TotalCheck.lean
import Lean4Agent.TotalCheck

#print axioms Lean4Agent.checkTotal_sound
#print axioms Lean4Agent.checkTotal_complete
#print axioms Lean4Agent.total_append
