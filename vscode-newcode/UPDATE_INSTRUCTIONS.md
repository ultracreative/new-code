I have updated the `package.json` file for the VS Code extension. Now, when you type `"` in a `.nc` file, it should automatically insert `「」` with the cursor placed in between.

To apply this change, please follow these steps:

1.  **Navigate to the extension directory:**
    `cd /Users/danrodriguez/Desktop/new-code/vscode-newcode`
2.  **Re-package the extension:**
    `vsce package`
    This will create a new `.vsix` file (e.g., `vscode-newcode-0.1.0.vsix`).
3.  **Install the updated extension in VS Code:**
    *   Open VS Code.
    *   Go to the Extensions view (`Ctrl+Shift+X` or `Cmd+Shift+X`).
    *   Click on the three dots (...) in the top-right corner.
    *   Select "Install from VSIX...".
    *   Navigate to `/Users/danrodriguez/Desktop/new-code/vscode-newcode/` and select the newly created `.vsix` file.
    *   If you had the previous version installed, VS Code might ask you to update or replace it. Confirm the update.
4.  **Reload VS Code.**

After these steps, open a `.nc` file and try typing `"`. It should now insert `「」` and place your cursor in the middle.