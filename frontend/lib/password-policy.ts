/** Client-side mirror of `validate_password_policy` in
 * backend/app/schemas/auth.py (NIST 800-63B style: length + letter + digit,
 * no forced character classes). The server remains authoritative; checking
 * here lets a form explain the rule before a round trip. */

export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_MAX_LENGTH = 255;

export type PasswordIssue = "tooShort" | "tooLong" | "needsLetterAndDigit" | "containsEmail";

export function passwordIssue(password: string, email?: string | null): PasswordIssue | null {
  if (password.length < PASSWORD_MIN_LENGTH) return "tooShort";
  if (password.length > PASSWORD_MAX_LENGTH) return "tooLong";
  if (!/\p{L}/u.test(password) || !/\p{Nd}/u.test(password)) return "needsLetterAndDigit";
  const local = (email ?? "").split("@")[0].toLowerCase();
  if (local.length >= 4 && password.toLowerCase().includes(local)) return "containsEmail";
  return null;
}
