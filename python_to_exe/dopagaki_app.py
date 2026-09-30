"""Dopagaki entrypoint integration with the shared Converter/Editor actions."""

if __package__:
    from .converter_gui import TASConverterApp
    from .editor.dopagaki.ui import DopagakiEditorWindow
else:
    from converter_gui import TASConverterApp
    from editor.dopagaki.ui import DopagakiEditorWindow


class DopagakiApp(TASConverterApp):
    editor_class = DopagakiEditorWindow
