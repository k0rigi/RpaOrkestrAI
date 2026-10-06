"""File selection that keeps launch shortcuts and their embedded arguments intact."""

from __future__ import annotations

import platform


def _windows_launch_dialog():
    import clr

    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import OpenFileDialog

    dialog = OpenFileDialog()
    # Resolving a .lnk here discards its arguments and working directory.
    dialog.DereferenceLinks = False
    dialog.Multiselect = False
    dialog.CheckFileExists = True
    dialog.RestoreDirectory = True
    dialog.Title = "Açılacak uygulama, kısayol veya dosyayı seçin"
    dialog.Filter = "Tüm dosyalar (*.*)|*.*"
    return dialog


def choose_path(webview, window, kind: str, *, preserve_shortcuts: bool = False):
    if platform.system() == "Windows" and kind == "open" and preserve_shortcuts:
        from System import Action
        from System.Windows.Forms import DialogResult

        selected = None

        def show():
            nonlocal selected
            dialog = _windows_launch_dialog()
            try:
                if dialog.ShowDialog(window.native) == DialogResult.OK:
                    selected = str(dialog.FileName)
            finally:
                dialog.Dispose()

        # FastAPI runs on a worker; the native dialog must use the owner's STA UI thread.
        window.native.Invoke(Action(show))
        return selected

    kinds = getattr(webview, "FileDialog", None)
    dialog = {"open": getattr(kinds, "OPEN", 10), "folder": getattr(kinds, "FOLDER", 20),
              "save": getattr(kinds, "SAVE", 30)}[kind]
    chosen = window.create_file_dialog(dialog)
    return (chosen if isinstance(chosen, str) else chosen[0]) if chosen else None
