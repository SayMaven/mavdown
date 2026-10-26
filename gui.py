"""
Mavdown GUI Gateway (v1.3.0)
Re-exports App from the modular ui/ package.
"""
from ui import App, APP_VERSION, APP_TITLE

__all__ = ["App", "APP_VERSION", "APP_TITLE"]

if __name__ == "__main__":
    app = App()
    app.mainloop()
