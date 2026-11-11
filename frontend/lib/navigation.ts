/** Full-page navigation to an external URL (a bank's consent screen, say).
 * Indirected through one function because jsdom's window.location is
 * unforgeable, which makes the call impossible to stub in tests. */
export function navigateAway(url: string) {
  window.location.assign(url);
}
