# New Code — VS Code extension

Language support for **New Code** (`.nc` files): syntax highlighting, diagnostics, completion, hover, and document outline.

## What you get

- **Syntax highlighting** for `fn`, `let`, `process`, `module`, the clause keywords (`intent` / `forbid` / `ensure` / `requires` / `emits` / `consumes` / `guard`), the type atoms (𝕎, ℝ, ℕ, ℤ, 𝔹), the bind symbols (`≔` / `:=`), arrows (`→` / `->`), the `??` hole, the operator glyphs (⊕, ⊚, ⇝, ⌊·⌉, ⟪·,·⟫, d_γ, ⁻, ▶, ∥, ↺, ▷◁), intent-string brackets (「…」, 『…』), and stdlib / shape names.
- **Diagnostics** from the parser, published live on change and save.
- **Completion** for declaration keywords at line start, clause keywords at indent, stdlib names and shapes in expression contexts, type atoms.
- **Hover** tooltips with the detail / docs for any stdlib name, any user-declared `fn`, `let`, `process`, or `module` (including its intent block), and the clause keywords themselves.
- **Document symbols** for the outline view and the file picker.

The bridge is the Python-based Language Server (`newcode.lsp`) shipped in the main package. This extension is thin on top of it.

## Install

Prerequisites:

- VS Code 1.75+
- Node 18+ (for `npm install` during the one-time bundle step)
- Python 3.10+
- `newcode` installed in an environment visible to the `python` command (`pip install -e .` from the repo root).

From this directory:

```bash
npm install
```

Then in VS Code:

- Open the repo root.
- Press **F5**. An Extension Development Host opens with the extension loaded.
- In the Host, open any `.nc` file. You should get highlighting and diagnostics immediately.

To package a distributable `.vsix`:

```bash
npx vsce package
```

## Configure

All settings live under `newcode.lsp.*`:

| Setting | Default | What it does |
|---|---|---|
| `newcode.lsp.command` | `"python"` | Command used to launch the LSP server. |
| `newcode.lsp.args`    | `["-m", "newcode.lsp"]` | Arguments passed to that command. |
| `newcode.lsp.enabled` | `true` | Master switch. |

If `python` is not on your PATH, set `newcode.lsp.command` to the absolute path of the Python interpreter where `newcode` is installed. In a virtualenv this will be something like `/path/to/.venv/bin/python`.

## How it talks to Python

On activation, the extension spawns:

```
<newcode.lsp.command> <newcode.lsp.args...>
```

and connects a `vscode-languageclient` over that process's stdio. The server speaks standard LSP (`initialize`, `textDocument/didOpen`, `textDocument/didChange`, `textDocument/completion`, `textDocument/hover`, `textDocument/documentSymbol`, diagnostics).

If activation fails (the interpreter is wrong, `newcode` is not installed, the port is blocked), VS Code surfaces the error and the extension logs to the **New Code** output channel.

## Notes on the TextMate grammar

The grammar in `syntaxes/newcode.tmLanguage.json` is intentionally small. It is the fast-path highlighter VS Code uses before the LSP is ready. The authoritative highlighting comes from the LSP's semantic tokens in later versions; the TextMate grammar is the safety net.
