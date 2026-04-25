// vscode-newcode
//
// Thin VS Code extension for the New Code language. Declares the language
// (via package.json + the TextMate grammar) and starts the Python-based
// language server when a .nc file is opened.
//
// Install:
//   1) In this directory: `npm install`
//   2) Open the repo root in VS Code, press F5 to launch an Extension
//      Development Host, or `vsce package` to bundle a .vsix.
//
// Settings:
//   newcode.lsp.command  (default "python")
//   newcode.lsp.args     (default ["-m", "newcode.lsp"])
//   newcode.lsp.enabled  (default true)

const vscode = require("vscode");
const { workspace, window, commands, Selection } = require("vscode");
const {
  LanguageClient,
  TransportKind,
} = require("vscode-languageclient/node");

/** @type {import('vscode-languageclient/node').LanguageClient | null} */
let client = null;

function activate(context) {
  const japaneseBracketDecoration = vscode.window.createTextEditorDecorationType({
    color: new vscode.ThemeColor("newcode.japaneseBracketForeground"),
  });

  const findJapaneseBracketRanges = (document) => {
    if (document.languageId !== "newcode") {
      return [];
    }

    const text = document.getText();
    const matches = text.matchAll(/[「」『』]/g);
    const ranges = [];

    for (const match of matches) {
      const start = document.positionAt(match.index);
      const end = document.positionAt(match.index + match[0].length);
      ranges.push(new vscode.Range(start, end));
    }

    return ranges;
  };

  const updateJapaneseBracketDecorations = (editor) => {
    if (!editor || editor.document.languageId !== "newcode") {
      return;
    }

    editor.setDecorations(
      japaneseBracketDecoration,
      findJapaneseBracketRanges(editor.document),
    );
  };

  const refreshVisibleJapaneseBracketDecorations = () => {
    for (const editor of vscode.window.visibleTextEditors) {
      updateJapaneseBracketDecorations(editor);
    }
  };

  context.subscriptions.push(japaneseBracketDecoration);

  const insertJapaneseBrackets = async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== "newcode") {
      return;
    }

    const selections = editor.selections;
    await editor.edit((editBuilder) => {
      for (const selection of selections) {
        if (selection.isEmpty) {
          editBuilder.insert(selection.active, "「」");
        } else {
          const selectedText = editor.document.getText(selection);
          editBuilder.replace(selection, `「${selectedText}」`);
        }
      }
    });

    editor.selections = selections.map((selection) => {
      if (selection.isEmpty) {
        const cursor = selection.active.translate(0, 1);
        return new Selection(cursor, cursor);
      }

      const start = selection.start.translate(0, 1);
      const end = selection.end.translate(0, 1);
      return new Selection(start, end);
    });
  };

  context.subscriptions.push(
    commands.registerCommand("newcode.insertJapaneseBrackets", insertJapaneseBrackets),
  );

  context.subscriptions.push(
    commands.registerCommand("type", async (args) => {
      const editor = vscode.window.activeTextEditor;
      if (
        editor &&
        editor.document.languageId === "newcode" &&
        args &&
        args.text === "\""
      ) {
        await insertJapaneseBrackets();
        return;
      }

      await commands.executeCommand("default:type", args);
    }),
  );

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      updateJapaneseBracketDecorations(editor);
    }),
  );

  context.subscriptions.push(
    vscode.window.onDidChangeVisibleTextEditors(() => {
      refreshVisibleJapaneseBracketDecorations();
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((event) => {
      const editor = vscode.window.visibleTextEditors.find(
        (visibleEditor) => visibleEditor.document === event.document,
      );
      updateJapaneseBracketDecorations(editor);
    }),
  );

  refreshVisibleJapaneseBracketDecorations();

  const config = workspace.getConfiguration("newcode.lsp");
  if (!config.get("enabled", true)) {
    window.showInformationMessage(
      "New Code language server is disabled (newcode.lsp.enabled = false).",
    );
    return;
  }

  const command = config.get("command", "python");
  const args = config.get("args", ["-m", "newcode.lsp"]);

  const serverOptions = {
    command,
    args,
    transport: TransportKind.stdio,
  };

  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "newcode" }],
    synchronize: {
      fileEvents: workspace.createFileSystemWatcher("**/*.nc"),
    },
    outputChannelName: "New Code",
  };

  client = new LanguageClient(
    "newcode",
    "New Code",
    serverOptions,
    clientOptions,
  );

  client
    .start()
    .catch((err) => {
      window.showErrorMessage(
        `Failed to start New Code language server: ${err.message}. ` +
          `Is newcode installed and on PATH? (pip install -e .)`,
      );
    });
}

function deactivate() {
  if (!client) return undefined;
  return client.stop();
}

module.exports = { activate, deactivate };
