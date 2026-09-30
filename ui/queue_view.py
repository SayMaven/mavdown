import customtkinter as ctk
from ui.constants import THEME

def build_queue_view(app, parent):
    """
    Membangun tampilan Antrean Unduhan Massal (Batch Download Manager).
    """
    queue_view = ctk.CTkFrame(parent, fg_color=THEME["card_bg"], corner_radius=14)

    qi = ctk.CTkFrame(queue_view, fg_color="transparent")
    qi.pack(fill="both", expand=True, padx=16, pady=16)

    hdr = ctk.CTkFrame(qi, fg_color="transparent")
    hdr.pack(fill="x", pady=(0, 10))

    ctk.CTkLabel(
        hdr, text="Manajer Antrean Unduhan Massal (Batch Queue)",
        font=ctk.CTkFont(family="Inter", size=14, weight="bold"), text_color=THEME["text_title"]
    ).pack(side="left")

    ctk.CTkButton(
        hdr, text="Kosongkan Antrean", command=app._clear_queue_input,
        width=130, height=28, corner_radius=6, font=ctk.CTkFont(size=11),
        fg_color="#1E2032", hover_color="#2B2E45", text_color=THEME["accent_rose"]
    ).pack(side="right")

    ctk.CTkLabel(
        qi, text="Tempelkan daftar URL (satu link per baris), lalu klik 'Tambahkan ke Antrean' dan 'Mulai Semua'.",
        font=ctk.CTkFont(size=11), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 8))

    app.queue_textbox = ctk.CTkTextbox(
        qi, height=130, font=ctk.CTkFont(family="Consolas", size=11),
        fg_color=THEME["card_inner"], text_color=THEME["text_body"],
        border_color=THEME["border"], border_width=1, corner_radius=8
    )
    app.queue_textbox.pack(fill="x", pady=(0, 10))

    btn_row = ctk.CTkFrame(qi, fg_color="transparent")
    btn_row.pack(fill="x", pady=(0, 12))

    ctk.CTkButton(
        btn_row, text="Tambahkan ke Antrean", command=app._add_to_queue,
        height=36, corner_radius=8, fg_color=THEME["accent_indigo"], hover_color=THEME["accent_indigo_hover"],
        font=ctk.CTkFont(size=12, weight="bold")
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(
        btn_row, text="Mulai Semua Unduhan", command=app._start_queue,
        height=36, corner_radius=8, fg_color=THEME["accent_emerald"], hover_color=THEME["accent_emerald_hover"],
        font=ctk.CTkFont(size=12, weight="bold")
    ).pack(side="left")

    ctk.CTkButton(
        btn_row, text="Import File .txt", command=app._import_queue_txt,
        height=36, corner_radius=8, fg_color="#1E2032", hover_color="#2B2E45",
        font=ctk.CTkFont(size=11)
    ).pack(side="right")

    # Scrollable Queue List
    ctk.CTkLabel(
        qi, text="DAFTAR ANTREAN AKTIF",
        font=ctk.CTkFont(size=10, weight="bold"), text_color="#4B5563"
    ).pack(anchor="w", pady=(0, 4))

    app.queue_list_frame = ctk.CTkScrollableFrame(qi, fg_color=THEME["card_inner"], corner_radius=8)
    app.queue_list_frame.pack(fill="both", expand=True)

    return queue_view
