import customtkinter as ctk
from ui.constants import THEME

def build_log_view(app, parent):
    """
    Membangun tampilan Konsol Terminal / Log output.
    """
    log_view = ctk.CTkFrame(parent, fg_color=THEME["card_bg"], corner_radius=14)

    li = ctk.CTkFrame(log_view, fg_color="transparent")
    li.pack(fill="both", expand=True, padx=16, pady=16)

    hdr = ctk.CTkFrame(li, fg_color="transparent")
    hdr.pack(fill="x", pady=(0, 10))

    ctk.CTkLabel(
        hdr, text="Konsol Terminal & Output Eksekusi",
        font=ctk.CTkFont(family="Inter", size=14, weight="bold"), text_color=THEME["text_title"]
    ).pack(side="left")

    ctk.CTkButton(
        hdr, text="Bersihkan Log", command=app.clear_log,
        width=100, height=28, corner_radius=6, font=ctk.CTkFont(size=11),
        fg_color="#1E2032", hover_color="#2B2E45", text_color=THEME["text_muted"]
    ).pack(side="right", padx=(6, 0))

    ctk.CTkButton(
        hdr, text="Salin Semua", command=app.copy_log,
        width=90, height=28, corner_radius=6, font=ctk.CTkFont(size=11),
        fg_color="#1E2032", hover_color="#2B2E45", text_color=THEME["text_muted"]
    ).pack(side="right")

    app.log_area = ctk.CTkTextbox(
        li, font=ctk.CTkFont(family="Consolas", size=11),
        fg_color="#080910", text_color="#D1D5DB",
        border_color=THEME["border"], border_width=1, corner_radius=8
    )
    app.log_area.pack(fill="both", expand=True)

    return log_view
