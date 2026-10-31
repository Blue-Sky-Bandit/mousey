# Mousey testing session

**Session 1 done (2026-10-31).** Results are in STATUS.md ("Testing session 1"). For the
next session, after building a new zip, only these are left:

- [x] **Tester on Finals (profile 4):** passed 2026-10-31. press every button. Thumb back should tick "Thumb
  back", DPI up "DPI up" (both were mixed up by the UK keyboard layout; now fixed). Key
  names should show `#` where a US keyboard would say `\`. Then press the profile button
  while the tester is open: it should switch to the new profile and clear its ticks.
- [ ] **First start without a mouse, fresh PC (optional):** on a PC that has never run
  Mousey, start it with the mouse unplugged: a "Plug in your G502 HERO" page, no error
  pop-up; plugging the mouse in reads it.
- [x] **Factory profiles 1 and 2 lighting:** done 2026-10-31 (cycle; breathing #00DCFF; 0 = full). reset a spare profile to *Factory profile 1*
  (and later 2), write, and note what the lights do (these store brightness 0). Restore
  afterwards from the Backups window.
- [ ] **Host-mode recovery:** parked for now (user).

The full plan from session 1 follows, for reference.

---

Everything built since the last hands-on session, in a safe order. Each test says what to
do, what should happen, and what to note. Tick the box when done and jot what you saw
next to anything that didn't match.

**Profiles to use.** Profile 3 ("Test profile") is the test subject and profile 2 is the
spare for copy/swap. Leave profile 4 ("Finals") alone. Everything gets put back at the end
(test 19).

**Time needed:** about 45–60 minutes.

---

## Before you start

- [ ] **0.1 G Hub closed.** Make sure G Hub isn't running (system tray too). Its updater
  service can stay. Mousey refuses to write while G Hub runs.
- [ ] **0.2 Dynamic Lighting off** for the mouse (Settings → Personalization → Dynamic
  Lighting), otherwise lighting tests will look wrong.
- [ ] **0.3 Mouse plugged in** by cable.
- [ ] **0.4 Extract the release.** Copy `A:\Personal\Claude\MouseSoftware\dist\Mousey-0.9.0.zip`
  to e.g. Documents, right-click → **Extract All…**. You should get one `Mousey` folder
  containing `Mousey.exe`, `_internal`, `START HERE.txt` and `LICENSE.txt`.
  *Note:* anything unexpected in the folder.

All tests below use this extracted `Mousey.exe`, not the development version.

---

## Part A: start-up and reading (no writes)

- [ ] **1. Running from inside the zip (expected to fail).** Open the zip in Explorer
  without extracting and double-click `Mousey.exe` inside it.
  *Expected:* it doesn't start; Windows or the launcher shows an error (it can't find
  `_internal`), or Windows offers to extract.
  *Note:* the exact message, so the README can quote it.

- [ ] **2. First launch, SmartScreen.** Run `Mousey.exe` from the extracted folder.
  *Expected:* possibly "Windows protected your PC" → **More info → Run anyway** (once only).
  *Note:* whether it appeared.

- [ ] **3. Splash, mouse plugged in.**
  *Expected:* the FLYHT Studios neon sign plays for about 4 seconds, smoothly; "Reading
  the mouse…" then "Ready" above a cyan bar that fills to the end; "Mousey 0.9.0" bottom
  left. Then the main window opens.
  *Note:* smoothness, timing, how the text/bar look, anything clipped or flickering.

- [ ] **4. Main window and icon.**
  *Expected:* the yellow mouse icon with the "A" in the title bar and on the taskbar (its
  own taskbar entry, not Python's); header says "*your mouse name* connected"; the profile
  in use shows **In use** in the sidebar.
  Optional: right-click the taskbar icon → **Pin to taskbar**, close, and start Mousey from
  the pin.

- [ ] **5. Back up now.** Press **Back up now**.
  *Expected:* "Backup saved" with a path in `%APPDATA%\Mousey\backups` (the new folder).
  This is your **start-of-session backup**; note its time.

- [ ] **6. Backups window.** Press **Backups…**.
  *Expected:* a timeline grouped by day; the new backup at the top with a **yellow dot**
  and "matches the mouse"; the older backups from 29 October below it marked "(older
  folder)", each with a summary of what changed. Click a few to see the change lists.
  Close it without restoring.

- [ ] **7. Diagnostics.** More → **Save diagnostics…**, save to the Desktop, open it.
  *Expected:* versions, both data folders with file counts, Logitech processes running,
  the mouse's firmware, mode "onboard", profile in use, sector list. No profile settings.

- [ ] **8. Live tracking.** Press the profile button a few times.
  *Expected:* the **In use** label follows within about a second. Return to profile 3.

- [ ] **9. Button tester (reading only).** Buttons tab → **Test buttons…**. Point at the
  pad and press every button, including both wheel tilts.
  *Expected:* each button that sends something to the PC ticks its row and appears in
  the log; DPI, profile and sniper (DPI shift) are marked "inside the mouse".
  **Check carefully:** tilting the wheel **left** should tick "Wheel tilt left" and log
  "Scroll left" (and right → right). The direction is a guess in the code.
  *Note:* any button that doesn't tick, and whether tilt left/right are swapped.

- [ ] **10. Safety locks (no writes).**
  a. Buttons tab, profile 3: click the main **Left click** action. *Expected:* it shows
     "Left click 🔒" and won't open the editor.
  b. Profile tab: with the mouse on profile 3, try to switch profile 3 to **Deactivated**.
     *Expected:* refused, "in use on the mouse".
  c. Undo any changes (footer **Undo all**).

---

## Part B: writes on profile 3 (each one previews first; confirm only if the preview matches)

For every write: the preview should list exactly the change you made, in plain words.
After writing you should get "Written and checked" with a backup path.

- [ ] **11. Single-layer mode, sniper as a key.** Profile 3, Buttons tab: make sure
  **G-Shift second layer** is off. Click the sniper button's action → Keyboard key → **F**.
  Write.
  *Expected:* preview shows "Sniper button: DPI shift (sniper) → F". After writing, open
  Notepad (or the button tester) and press sniper: it types **f**.

- [ ] **12. G-Shift with a second-layer action.** Turn **G-Shift second layer** on (sniper
  becomes G-Shift automatically). Set the G-Shift action for **Thumb back** to
  **Ctrl+V** (Keyboard key, tick Ctrl, key V). Write.
  *Expected:* preview shows G-Shift layer Off → On, Sniper button F → G-Shift, and the
  thumb back G-Shift action. Copy some text, then in Notepad **hold sniper and press thumb
  back**: it pastes. Thumb back alone still goes Back.

- [ ] **13. DPI.** DPI tab, profile 3: change level 2 from 2400 to **1600**, make level 2
  the default. Write.
  *Expected:* the pointer is noticeably slower on profile 3; pressing DPI up/down steps
  through the levels (DPI lights change).

- [ ] **14. Lighting effects.** Lighting tab, profile 3: logo **Breathing** in a colour of
  your choice, DPI lights **Off**. Write.
  *Expected:* the logo breathes, the DPI lights are off (Dynamic Lighting must be off).

- [ ] **15. Library.** Library tab: **Save Profile 3 to library…**, name it "Test 1". Then
  select profile 2, Library tab → **Load into Profile 2** on "Test 1". Don't write yet;
  check the Buttons/DPI/Lighting tabs show the Test 1 settings on profile 2, then **Undo
  changes to this profile**.
  *Expected:* the saved card appears with a Delete button; loading and undo work.

- [ ] **16. Copy and swap.** Profile tab, profile 3: **Swap with another profile… →
  Profile 2**. Write.
  *Expected:* the preview lists changes to both Profile 2 and Profile 3; after writing,
  profile 2 behaves like your test profile (sniper is G-Shift, etc.) and profile 3 like
  the old profile 2. Check with the profile button and the tester.

- [ ] **17. Factory reset.** Select profile 3, Profile tab → **Reset to factory
  settings… → Factory profile 3**. Write.
  *Expected:* profile 3 gets the factory layout and its name becomes blank.
  **Watch the lights:** the factory profiles store the colour cycle with brightness **0**.
  *Note:* what the lights do on profile 3 now (off? dim? full cycle?).

---

## Part C: restore, power and recovery

- [ ] **18. Power-up profile.** Unplug and replug the mouse three times, each time from a
  different profile (e.g. on 2, on 3, on 5).
  *Expected:* Mousey shows "unplugged", then reads the mouse again when it comes back.
  *Note:* which profile the mouse starts on each time (does it always start on profile 1?).

- [ ] **19. Restore everything (Backups window).** Press **Backups…**, select your
  **start-of-session backup** from test 5, **Restore this backup…**. Tick everything it
  offers, check the preview, write.
  *Expected:* the preview lists all the test changes being undone (profiles 2 and 3);
  after writing, the timeline's top entry is a "Before a restore" backup and your
  start-of-session backup now shows **matches the mouse** (yellow dot).

- [ ] **20. Splash with the mouse unplugged.** Close Mousey, unplug the mouse, start
  Mousey.
  *Expected:* the full 4-second splash with "Mouse not found" at the end, then the window
  opens showing the newest backup with a "No G502 HERO found" message. Plug the mouse in:
  it should be read automatically.

- [ ] **21. Host-mode recovery (optional, only if it ever happens).** If you ever find the
  mouse ignoring its profiles after using G Hub, Mousey should show a banner "The mouse is
  in host mode" with **Switch to onboard memory**. Quit G Hub, press it, confirm.
  *Expected:* banner disappears and the profiles work again. (Don't open G Hub just to
  test this; it can overwrite the mouse's profiles.)

---

## After the session

Tell me the results, especially:
- anything marked *Note* above (zip error text, SmartScreen, tilt direction, factory
  brightness 0, power-up profile, splash smoothness);
- any step where the preview didn't match what you changed, or anything failed.

If anything goes wrong mid-way, stop there: Mousey always saves a backup before writing,
and the Backups window can put any of them back.
