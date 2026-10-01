"""Dopagaki entrypoint integration with the shared Converter/Editor actions."""

if __package__:
    from .converter_gui import TASConverterApp
    from .editor.dopagaki.ui import DopagakiEditorWindow
else:
    from converter_gui import TASConverterApp
    from editor.dopagaki.ui import DopagakiEditorWindow


class DopagakiApp(TASConverterApp):
    editor_class = DopagakiEditorWindow

    def observe_conversion(self, callback):
        # The shared app permits one converter run at a time. The receiver is
        # weak and generation-bound, so closing/replacing its Editor is safe.
        self._ritual_result_callback = callback

    def _conversion_result_received(self, success, payload):
        callback = getattr(self, "_ritual_result_callback", None)
        self._ritual_result_callback = None
        if callback is not None:
            try:
                callback(success, payload)
            except Exception:
                # A disappearing presentation must not swallow normal results
                # or replace existing converter error handling with audio errors.
                import traceback
                traceback.print_exc()
