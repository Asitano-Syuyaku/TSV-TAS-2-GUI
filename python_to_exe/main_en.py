if __package__:
    from .converter_gui import TASConverterApp
else:
    from converter_gui import TASConverterApp


if __name__ == "__main__":
    TASConverterApp("en").mainloop()
