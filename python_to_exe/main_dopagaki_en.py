if __package__:
    from .dopagaki_app import DopagakiApp
else:
    from dopagaki_app import DopagakiApp


if __name__ == "__main__":
    DopagakiApp("en").mainloop()
