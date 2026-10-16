if __package__:
    from .display import enable_dpi_awareness
else:
    from display import enable_dpi_awareness

# Before any Tk window exists: crisp text on scaled Windows displays.
enable_dpi_awareness()

if __package__:
    from .converter_gui import TASConverterApp
else:
    from converter_gui import TASConverterApp


if __name__ == "__main__":
    TASConverterApp("en").mainloop()
