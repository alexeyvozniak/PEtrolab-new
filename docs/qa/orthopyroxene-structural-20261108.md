# Structural orthopyroxene: native QA, 2026-11-08

- Windows Tauri development runtime, isolated `org.petrolab.opx-qa-20261108` profile; screenshot dimensions 1349 × 929 (not the requested 1363 × 936).
- The isolated project contains the published Tariat mean (n=22), imported as reported with FeOt; enstatite was explicitly assigned for this test. It is not an individual measured spot.
- The original bulk method remained the initial choice. The structural T/M1/M2 method was selected using the native select and keyboard, then calculated and saved with all Fe as Fe²⁺. The interface labels the formula and site allocations as a draft model, not mineral identification.
- The saved result was opened in the same session, then the application was closed and restarted. The saved structural calculation appeared again in its history. The source and measurements were not edited during this UI test; automated workflow tests independently verify their preservation.
- [Saved result](screenshots/opx-native-saved-20261108.jpg) and [expanded history](screenshots/opx-native-history-20261108.jpg).
- Packaged Windows sidecar passed the eight-method service gate. Automated tests cover invalid Fe modes and atomic Selection calculation through 100 analyses; these were not separately exercised in the native window.
- Exact 1363 × 936 visual acceptance and a complete native Tab/Enter traversal remain to be checked. The natural comparison does not independently validate all Fe³⁺ or site-allocation modes; the method remains `draft`.
