# Dynamic Difficulty Adjustment (Pseudocode)

```text
Initialize:
    current_level = 3              # any value in [1..5]
    min_level = 1
    max_level = 5

    consecutive_passes = 0
    consecutive_fails = 0

On each exercise_result(result):   # result is either "pass" or "fail"

    if result == "fail":
        consecutive_fails = consecutive_fails + 1
        consecutive_passes = 0

        if consecutive_fails >= 3:
            current_level = max(min_level, current_level - 1)
            consecutive_fails = 0   # reset streak after adjustment

    else if result == "pass":
        consecutive_passes = consecutive_passes + 1
        consecutive_fails = 0

        if consecutive_passes >= 5:
            current_level = min(max_level, current_level + 1)
            consecutive_passes = 0  # reset streak after adjustment

    return current_level
```

## Notes
- Difficulty is clamped to `1..5`.
- A fail breaks a pass streak, and a pass breaks a fail streak.
- Streak counter resets after level adjustment to avoid repeated immediate changes.
