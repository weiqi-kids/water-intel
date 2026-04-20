#!/bin/bash
# Test validate_docs.py against intentionally broken fixtures.
# Run from repo root: bash tests/test_validate_docs.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

run_test() {
    local name="$1"
    local expected_errors="$2"
    local fixture_dir="$3"

    output=$(cd "$SCRIPT_DIR" && python3 scripts/validate_docs.py --docs-path "$fixture_dir" 2>&1) || true
    error_count=$(echo "$output" | grep -c "^  ERROR:" || true)

    if [ "$error_count" -eq "$expected_errors" ]; then
        echo "  PASS: $name (got $error_count errors as expected)"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $name (expected $expected_errors errors, got $error_count)"
        echo "$output" | head -20
        FAIL=$((FAIL + 1))
    fi
}

echo "=== validate_docs.py test suite ==="

# --- Test 1: Invalid top-level directory ---
T1=$(mktemp -d)
mkdir -p "$T1/live/capacity-pricing" "$T1/invalid-dir"
cat > "$T1/live/capacity-pricing/merge.yaml" << 'EOF'
document_id: CP-MEM-LIVE
title_zh: test
main:
  zh: test.md
EOF
echo "# test" > "$T1/live/capacity-pricing/test.md"
run_test "invalid top-level directory" 2 "$T1"
rm -rf "$T1"

# --- Test 2: Missing merge.yaml ---
T2=$(mktemp -d)
mkdir -p "$T2/live/capacity-pricing"
echo "# test" > "$T2/live/capacity-pricing/test.md"
run_test "missing merge.yaml" 1 "$T2"
rm -rf "$T2"

# --- Test 3: Missing required fields ---
T3=$(mktemp -d)
mkdir -p "$T3/live/capacity-pricing"
cat > "$T3/live/capacity-pricing/merge.yaml" << 'EOF'
document_id: CP-MEM-LIVE
EOF
run_test "missing required fields (title_zh + main.zh)" 2 "$T3"
rm -rf "$T3"

# --- Test 4: Invalid document_id format ---
T4=$(mktemp -d)
mkdir -p "$T4/live/capacity-pricing"
cat > "$T4/live/capacity-pricing/merge.yaml" << 'EOF'
document_id: INVALID-FORMAT
title_zh: test
main:
  zh: test.md
EOF
echo "# test" > "$T4/live/capacity-pricing/test.md"
run_test "invalid document_id format" 2 "$T4"
rm -rf "$T4"

# --- Test 5: .md file missing ---
T5=$(mktemp -d)
mkdir -p "$T5/live/capacity-pricing"
cat > "$T5/live/capacity-pricing/merge.yaml" << 'EOF'
document_id: CP-MEM-LIVE
title_zh: test
main:
  zh: nonexistent.md
EOF
run_test "md file does not exist" 1 "$T5"
rm -rf "$T5"

# --- Test 6: Invalid YAML in merge.yaml ---
T6=$(mktemp -d)
mkdir -p "$T6/live/capacity-pricing"
printf 'document_id: CP-MEM-LIVE\ntitle_zh: test\nmain:\n  zh: [unclosed bracket\n' \
    > "$T6/live/capacity-pricing/merge.yaml"
run_test "invalid YAML in merge.yaml" 1 "$T6"
rm -rf "$T6"

# --- Test 7: Broken live_ref ---
T7=$(mktemp -d)
mkdir -p "$T7/weekly/2026-W16/capacity-pricing"
cat > "$T7/weekly/2026-W16/capacity-pricing/merge.yaml" << 'EOF'
document_id: CP-MEM-2026-W16
title_zh: test
main:
  zh: test.md
live_ref: CP-MEM-LIVE
EOF
echo "# test" > "$T7/weekly/2026-W16/capacity-pricing/test.md"
run_test "live_ref points to non-existent document" 1 "$T7"
rm -rf "$T7"

# --- Test 8: Forbidden investment phrase ---
T8=$(mktemp -d)
mkdir -p "$T8/weekly/2026-W16/industry-report"
cat > "$T8/weekly/2026-W16/industry-report/merge.yaml" << 'EOF'
document_id: WR-MEM-2026-W16
title_zh: test
main:
  zh: test.md
EOF
printf "# 報告\n\n建議買入記憶體股" > "$T8/weekly/2026-W16/industry-report/test.md"
run_test "forbidden investment phrase" 1 "$T8"
rm -rf "$T8"

# --- Test 9: Invalid company directory name ---
T9=$(mktemp -d)
mkdir -p "$T9/companies/WINBOND/profile"
cat > "$T9/companies/WINBOND/profile/merge.yaml" << 'EOF'
document_id: PR-MEM-WINBOND
title_zh: test
main:
  zh: test.md
EOF
echo "# test" > "$T9/companies/WINBOND/profile/test.md"
run_test "invalid company directory name (uppercase)" 1 "$T9"
rm -rf "$T9"

# --- Test 10: type field mismatch ---
T10=$(mktemp -d)
mkdir -p "$T10/live/capacity-pricing"
cat > "$T10/live/capacity-pricing/merge.yaml" << 'EOF'
document_id: CP-MEM-LIVE
title_zh: test
main:
  zh: test.md
type: SD
EOF
echo "# test" > "$T10/live/capacity-pricing/test.md"
run_test "type field mismatches document_id prefix" 1 "$T10"
rm -rf "$T10"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
