const monaco = {
  editor: {
    create: () => ({
      dispose: () => {},
      getModel: () => ({
        getValue: () => '',
        setValue: () => {},
        onDidChangeContent: () => ({ dispose: () => {} }),
      }),
      addCommand: () => {},
      focus: () => {},
      layout: () => {},
      onDidBlurEditorWidget: () => ({ dispose: () => {} }),
      getPosition: () => ({ lineNumber: 1, column: 1 }),
      setPosition: () => {},
      executeEdits: () => true,
      trigger: () => {},
      getSelection: () => ({}),
    }),
    createModel: () => ({
      dispose: () => {},
      onDidChangeContent: () => ({ dispose: () => {} }),
    }),
    setModelLanguage: () => {},
    defineTheme: () => {},
    setTheme: () => {},
  },
  languages: {
    register: () => ({ dispose: () => {} }),
    setMonarchTokensProvider: () => {},
    registerCompletionItemProvider: () => ({ dispose: () => {} }),
  },
  Uri: {
    parse: (s: string) => ({ toString: () => s }),
  },
};

export default monaco;
export const editor = monaco.editor;
export const languages = monaco.languages;
export const Uri = monaco.Uri;
export type IStandaloneCodeEditor = any;
export type ITextModel = any;
export type Position = any;
export type ISelection = any;
