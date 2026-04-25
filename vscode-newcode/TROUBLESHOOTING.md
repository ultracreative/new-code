It seems the keybinding is still not taking effect. Let's try some troubleshooting steps:

1.  **Perform a full VS Code restart:**
    *   Completely close all VS Code windows.
    *   Reopen VS Code. A "Reload Window" is often not enough for extension changes to take full effect.

2.  **Verify the Language ID:**
    *   Open a `.nc` file in VS Code.
    *   Look at the bottom-right corner of the VS Code status bar. It should display "New Code" or "newcode" as the language mode. If it shows something else (e.g., "Plain Text"), then the `when` clause `editorLangId == 'newcode'` will not activate the keybinding.

3.  **Check for Keybinding Conflicts (Advanced):**
    *   Open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`).
    *   Type "Open Keyboard Shortcuts (JSON)" and select it.
    *   In the `keybindings.json` file, search for `"key": ""`. See if there are any other keybindings that might be overriding the one from the "New Code" extension, especially with a `when` clause that might take precedence.

Please try the full restart and verify the language ID first. Let me know the results.