"""Compare canonical native geometry without fragile coincident-solid Boolean operations."""

import math


def compare_brep_geometry(left, right):
    left_tokens = left.cleaned().exportBrepToString().split()
    right_tokens = right.cleaned().exportBrepToString().split()
    result = {
        "equal": False, "method": "cleaned BRep topology/curve/surface token comparison",
        "absolute_tolerance_mm": 1e-12, "relative_tolerance": 1e-12,
        "numeric_roundoff_tokens": 0, "maximum_numeric_roundoff": 0.0,
    }
    if len(left_tokens) != len(right_tokens):
        return result
    for left_token, right_token in zip(left_tokens, right_tokens):
        if left_token == right_token:
            continue
        try:
            a, b = float(left_token), float(right_token)
        except ValueError:
            return result
        if not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12):
            return result
        result["numeric_roundoff_tokens"] += 1
        result["maximum_numeric_roundoff"] = max(result["maximum_numeric_roundoff"], abs(a - b))
    result["equal"] = True
    return result
