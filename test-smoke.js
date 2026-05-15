/**
 * 最小限のスモークテスト（外部依存なし）
 */

const { add, subtract } = require("./src/app");

let passed = 0;
let failed = 0;

function assert(name, actual, expected) {
  if (actual === expected) {
    console.log(`  ✓ ${name}`);
    passed++;
  } else {
    console.error(`  ✗ ${name}: expected ${expected}, got ${actual}`);
    failed++;
  }
}

console.log("Running smoke tests...\n");

assert("add(1, 2) === 3", add(1, 2), 3);
assert("add(-1, 1) === 0", add(-1, 1), 0);
assert("subtract(5, 3) === 2", subtract(5, 3), 2);
assert("subtract(0, 0) === 0", subtract(0, 0), 0);

console.log(`\nResults: ${passed} passed, ${failed} failed`);

if (failed > 0) {
  process.exit(1);
}
