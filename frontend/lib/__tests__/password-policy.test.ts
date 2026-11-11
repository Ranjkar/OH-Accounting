import { describe, expect, test } from "vitest";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordIssue } from "../password-policy";

// Same rules the backend enforces in validate_password_policy
// (backend/app/schemas/auth.py); the two must agree or a form would promise
// a password the server then rejects.
describe("passwordIssue", () => {
  test("accepts a long password with a letter and a digit", () => {
    expect(passwordIssue("Correct-Horse-4")).toBeNull();
    expect(passwordIssue("a1".padEnd(PASSWORD_MIN_LENGTH, "x"))).toBeNull();
  });

  test("rejects anything shorter than the minimum", () => {
    expect(passwordIssue("Ab1".padEnd(PASSWORD_MIN_LENGTH - 1, "x"))).toBe("tooShort");
    expect(passwordIssue("")).toBe("tooShort");
  });

  test("rejects anything longer than the maximum", () => {
    expect(passwordIssue("A1".padEnd(PASSWORD_MAX_LENGTH + 1, "x"))).toBe("tooLong");
  });

  test("requires at least one letter and one digit", () => {
    expect(passwordIssue("abcdefghij")).toBe("needsLetterAndDigit");
    expect(passwordIssue("1234567890")).toBe("needsLetterAndDigit");
  });

  test("rejects a password containing the email local part", () => {
    expect(passwordIssue("jansen!2026", "jansen@voorbeeld.nl")).toBe("containsEmail");
    expect(passwordIssue("JANSEN!2026", "jansen@voorbeeld.nl")).toBe("containsEmail");
  });

  test("ignores short local parts, like the backend does", () => {
    expect(passwordIssue("jan-jan-2026", "jan@voorbeeld.nl")).toBeNull();
  });

  test("checks the minimum before the character classes", () => {
    expect(passwordIssue("abc")).toBe("tooShort");
  });
});
