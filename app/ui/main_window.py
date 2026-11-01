"""
Interfaccia Grafica Desktop Moderna per Windows (CustomTkinter)
==============================================================
Design ispirato ai moderni client di messaggistica Fluent/Dark Mode per Windows 11.
Supporta:
- Gestione Handshake e Richieste Chat
- Scambio chiavi X25519 e sblocco dinamico UI
- Visualizzazione messaggi E2EE con bolle chat dinamiche
- Minimizzazione e ripristino dalla System Tray
"""

import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import Optional, Dict, Any, List

from app.crypto.cipher_engine import CipherEngine
from app.database.local_storage import LocalStorage
from app.network.firebase_client import FirebaseClient
from app.utils.notifier import WindowsNotifier


# Configurazione Tema Globale
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")  # Verde smeraldo per accenti di sicurezza


class MainWindow(ctk.CTk):
    def __init__(
        self,
        storage: LocalStorage,
        firebase_client: FirebaseClient,
        notifier: WindowsNotifier,
        on_exit_callback: Optional[Any] = None,
    ):
        super().__init__()

        self.storage = storage
        self.firebase = firebase_client
        self.notifier = notifier
        self.on_exit_callback = on_exit_callback

        # Configurazione Finestra Principale
        self.title("SecureChat E2EE — Messaggistica Personale Cifrata")
        self.geometry("1050x700")
        self.minsize(850, 550)

        # Gestione chiusura finestra (Minimizza in System Tray)
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # Stato applicazione
        self.current_identity = self.storage.get_identity()
        self.selected_contact: Optional[Dict[str, Any]] = None
        self._is_closing = False

        # Inizializzazione Identita' se primo avvio
        if not self.current_identity:
            self._prompt_first_run_setup()

        # Layout Principale a Griglia (Sidebar a sinistra, Chat view a destra)
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_chat_panel()

        # Carica contatti iniziali
        self.refresh_contacts_list()

        # Avvia i listener di rete in background se Firebase e' collegato
        self._start_network_listeners()

    # =========================================================================
    # PRIMO AVVIO: Configurazione Profilo & Generazione Chiavi
    # =========================================================================
    def _prompt_first_run_setup(self) -> None:
        """Finestra modale al primo avvio per la generazione di GUID e chiavi X25519."""
        dialog = ctk.CTkInputDialog(
            text="Benvenuto in SecureChat E2EE!\n\nInserisci il tuo Nickname per generare l'identita' crittografica:",
            title="Inizializzazione Identita' E2EE",
        )
        nickname = dialog.get_input()
        if not nickname or not nickname.strip():
            nickname = f"User_{os.environ.get('USERNAME', 'Local')}"

        self.current_identity = self.storage.create_identity(nickname.strip())
        messagebox.showinfo(
            "Identita' Generata con Successo",
            f"GUID Univoco creato:\n{self.current_identity['guid']}\n\n"
            "La tua chiave asimmetrica X25519 e' stata creata e protetta a riposo sul PC con DPAPI.",
        )

    # =========================================================================
    # COSTRUZIONE UI: Sidebar Sinistra
    # =========================================================================
    def _build_sidebar(self) -> None:
        self.sidebar_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#18181b")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(3, weight=1)

        # 1. Header Profilo Utente
        profile_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#27272a", corner_radius=8)
        profile_frame.pack(fill="x", padx=12, pady=(12, 6))

        user_nick = self.current_identity["nickname"] if self.current_identity else "Utente"
        user_guid = self.current_identity["guid"] if self.current_identity else "user_0000"

        lbl_nick = ctk.CTkLabel(
            profile_frame,
            text=f"🔒 {user_nick}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ffffff",
        )
        lbl_nick.pack(anchor="w", padx=10, pady=(8, 0))

        # GUID con bottone copia rapida
        guid_frame = ctk.CTkFrame(profile_frame, fg_color="transparent")
        guid_frame.pack(fill="x", padx=10, pady=(2, 8))

        lbl_guid = ctk.CTkLabel(
            guid_frame,
            text=f"GUID: {user_guid[:16]}...",
            font=ctk.CTkFont(size=11),
            text_color="#a1a1aa",
        )
        lbl_guid.pack(side="left")

        btn_copy = ctk.CTkButton(
            guid_frame,
            text="Copia GUID",
            width=80,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color="#0d9488",
            hover_color="#0f766e",
            command=lambda: self._copy_to_clipboard(user_guid),
        )
        btn_copy.pack(side="right")

        # 2. Pulsanti Azioni Principali (+ Nuova Richiesta, Richieste Ricevute)
        action_btn_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        action_btn_frame.pack(fill="x", padx=12, pady=6)

        btn_new_request = ctk.CTkButton(
            action_btn_frame,
            text="+ Nuova Richiesta Chat",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0d9488",
            hover_color="#0f766e",
            command=self._show_new_chat_dialog,
        )
        btn_new_request.pack(fill="x", pady=2)

        self.btn_pending_req = ctk.CTkButton(
            action_btn_frame,
            text="Richieste Ricevute (0)",
            font=ctk.CTkFont(size=12),
            fg_color="#3f3f46",
            hover_color="#52525b",
            command=self._show_pending_requests_dialog,
        )
        self.btn_pending_req.pack(fill="x", pady=4)

        # 3. Label "Le tue conversazioni"
        lbl_chats = ctk.CTkLabel(
            self.sidebar_frame,
            text="CONVERSAZIONI E2EE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#71717a",
        )
        lbl_chats.pack(anchor="w", padx=16, pady=(10, 4))

        # 4. Scrollable frame contenente le card dei contatti
        self.contacts_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.contacts_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        # 5. Barra di stato inferiore (Firebase Status / Setup)
        status_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#27272a", height=38, corner_radius=0)
        status_frame.pack(fill="x", side="bottom")

        fb_connected = self.firebase.is_connected()
        fb_db_name = self.firebase.database_id or "(default)"
        fb_status_text = f"🟢 Firebase ({fb_db_name})" if fb_connected else "🔴 Firebase Non Connesso"
        self.lbl_firebase_status = ctk.CTkLabel(
            status_frame,
            text=fb_status_text,
            font=ctk.CTkFont(size=11),
            text_color="#34d399" if fb_connected else "#f87171",
        )
        self.lbl_firebase_status.pack(side="left", padx=10, pady=8)

        btn_cfg = ctk.CTkButton(
            status_frame,
            text="Configura",
            width=70,
            height=22,
            font=ctk.CTkFont(size=11),
            fg_color="#3f3f46",
            hover_color="#52525b",
            command=self._show_firebase_config_dialog,
        )
        btn_cfg.pack(side="right", padx=10, pady=8)

    # =========================================================================
    # COSTRUZIONE UI: Pannello Chat a Destra
    # =========================================================================
    def _build_chat_panel(self) -> None:
        self.chat_container = ctk.CTkFrame(self, fg_color="#09090b", corner_radius=0)
        self.chat_container.grid(row=0, column=1, sticky="nsew")
        self.chat_container.grid_rowconfigure(1, weight=1)
        self.chat_container.grid_columnconfigure(0, weight=1)

        # 1. Header Chat
        self.chat_header = ctk.CTkFrame(self.chat_container, fg_color="#18181b", height=60, corner_radius=0)
        self.chat_header.grid(row=0, column=0, sticky="ew")

        self.lbl_chat_title = ctk.CTkLabel(
            self.chat_header,
            text="Seleziona una chat",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ffffff",
        )
        self.lbl_chat_title.pack(side="left", padx=16, pady=(10, 0))

        self.lbl_chat_status = ctk.CTkLabel(
            self.chat_header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#10b981",
        )
        self.lbl_chat_status.pack(side="left", padx=(0, 16), pady=(12, 0))

        # 2. Area Messaggi (Scrollable)
        self.messages_scroll = ctk.CTkScrollableFrame(self.chat_container, fg_color="#09090b")
        self.messages_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        self.messages_scroll.grid_columnconfigure(0, weight=1)

        # 3. Banner Informativo per Handshake in attesa
        self.handshake_banner = ctk.CTkFrame(self.chat_container, fg_color="#854d0e", height=32, corner_radius=6)
        self.lbl_banner = ctk.CTkLabel(
            self.handshake_banner,
            text="⚠️ In attesa che il contatto accetti la richiesta di chat per scambiare le chiavi.",
            font=ctk.CTkFont(size=12),
            text_color="#fef08a",
        )
        self.lbl_banner.pack(padx=10, pady=4)

        # 4. Barra di Input Messaggio
        self.input_frame = ctk.CTkFrame(self.chat_container, fg_color="#18181b", height=65, corner_radius=0)
        self.input_frame.grid(row=2, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.txt_message = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Scrivi un messaggio cifrato E2EE...",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color="#27272a",
            border_color="#3f3f46",
        )
        self.txt_message.grid(row=0, column=0, padx=(16, 8), pady=12, sticky="ew")
        self.txt_message.bind("<Return>", lambda event: self._send_current_message())

        self.btn_send = ctk.CTkButton(
            self.input_frame,
            text="Invia",
            width=90,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0d9488",
            hover_color="#0f766e",
            command=self._send_current_message,
        )
        self.btn_send.grid(row=0, column=1, padx=(0, 16), pady=12)

        # Schermata di Benvenuto Default
        self._show_welcome_screen()

    def _show_welcome_screen(self) -> None:
        """Mostra placeholder quando nessuna chat e' selezionata."""
        for widget in self.messages_scroll.winfo_children():
            widget.destroy()

        welcome_frame = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        welcome_frame.pack(expand=True, pady=120)

        ctk.CTkLabel(
            welcome_frame,
            text="🛡️ SecureChat E2EE",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#2dd4bf",
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            welcome_frame,
            text="Messaggistica Personale Cifrata End-to-End con Architettura Serverless\n\n"
                 "• I messaggi sono cifrati con AES-256-GCM sul tuo PC prima di partire.\n"
                 "• Nessun server memorizza lo storico: la coda Firebase viene cancellata istantaneamente.\n"
                 "• Condividi il tuo GUID o invia una richiesta di chat per iniziare.",
            font=ctk.CTkFont(size=13),
            text_color="#a1a1aa",
            justify="center",
        ).pack()

        self.txt_message.configure(state="disabled")
        self.btn_send.configure(state="disabled")

    # =========================================================================
    # GESTIONE CONTATTI E LISTA CHAT
    # =========================================================================
    def refresh_contacts_list(self) -> None:
        """Ricarica la lista dei contatti dalla persistenza SQLite."""
        for widget in self.contacts_scroll.winfo_children():
            widget.destroy()

        contacts = self.storage.get_contacts()
        for contact in contacts:
            self._render_contact_card(contact)

        # Aggiorna contatore richieste pendenti
        pending = self.storage.get_pending_requests()
        count = len(pending)
        self.btn_pending_req.configure(
            text=f"Richieste Ricevute ({count})",
            fg_color="#0d9488" if count > 0 else "#3f3f46",
        )

    def _render_contact_card(self, contact: Dict[str, Any]) -> None:
        c_guid = contact["contact_guid"]
        status = contact["status"]

        is_selected = self.selected_contact and self.selected_contact["contact_guid"] == c_guid
        bg_color = "#27272a" if is_selected else "#18181b"

        card = ctk.CTkFrame(self.contacts_scroll, fg_color=bg_color, corner_radius=8, cursor="hand2")
        card.pack(fill="x", pady=3)

        # Bind click su tutta la card
        card.bind("<Button-1>", lambda e, c=contact: self._select_contact(c))

        header_box = ctk.CTkFrame(card, fg_color="transparent")
        header_box.pack(fill="x", padx=10, pady=(6, 2))
        header_box.bind("<Button-1>", lambda e, c=contact: self._select_contact(c))

        nick_lbl = ctk.CTkLabel(
            header_box,
            text=contact["nickname"],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff",
        )
        nick_lbl.pack(side="left")
        nick_lbl.bind("<Button-1>", lambda e, c=contact: self._select_contact(c))

        if status == "pending_sent":
            badge = ctk.CTkLabel(
                header_box, text="In attesa", font=ctk.CTkFont(size=10), text_color="#facc15"
            )
            badge.pack(side="right")
        elif status == "active":
            badge = ctk.CTkLabel(
                header_box, text="🔒 E2EE", font=ctk.CTkFont(size=10), text_color="#34d399"
            )
            badge.pack(side="right")

        # Preview ultimo messaggio
        preview_text = contact["last_message"] or ("Richiesta inviata..." if status == "pending_sent" else "Nessun messaggio")
        if len(preview_text) > 30:
            preview_text = preview_text[:30] + "..."

        lbl_preview = ctk.CTkLabel(
            card,
            text=preview_text,
            font=ctk.CTkFont(size=11),
            text_color="#a1a1aa",
        )
        lbl_preview.pack(anchor="w", padx=10, pady=(0, 6))
        lbl_preview.bind("<Button-1>", lambda e, c=contact: self._select_contact(c))

    def _select_contact(self, contact: Dict[str, Any]) -> None:
        """Seleziona un contatto e visualizza lo storico dei messaggi."""
        self.selected_contact = self.storage.get_contact(contact["contact_guid"])
        if not self.selected_contact:
            return

        self.refresh_contacts_list()

        # Configura Header
        self.lbl_chat_title.configure(text=self.selected_contact["nickname"])
        is_active = self.selected_contact["status"] == "active"

        if is_active:
            self.lbl_chat_status.configure(
                text="🔒 AES-256-GCM Sbloccato",
                text_color="#34d399",
            )
            self.handshake_banner.grid_forget()
            self.txt_message.configure(state="normal")
            self.btn_send.configure(state="normal")
            self.txt_message.focus_set()
        else:
            self.lbl_chat_status.configure(
                text="⏳ Handshake in attesa",
                text_color="#facc15",
            )
            self.handshake_banner.grid(row=1, column=0, sticky="n", padx=16, pady=4)
            self.txt_message.configure(state="disabled")
            self.btn_send.configure(state="disabled")

        # Carica Messaggi
        self._load_chat_messages(self.selected_contact["contact_guid"])
        self.storage.mark_chat_read(self.selected_contact["contact_guid"])

    def _load_chat_messages(self, contact_guid: str) -> None:
        """Popola l'area messaggi con i messaggi presenti nel database locale SQLite."""
        for widget in self.messages_scroll.winfo_children():
            widget.destroy()

        messages = self.storage.get_messages(contact_guid)
        for msg in messages:
            self._render_message_bubble(msg)

        # Auto-scroll all'ultimo messaggio
        self.after(50, lambda: self.messages_scroll._parent_canvas.yview_moveto(1.0))

    def _render_message_bubble(self, msg: Dict[str, Any]) -> None:
        is_out = msg["is_outgoing"]
        text = msg["text"]
        timestamp = msg["timestamp"]
        time_short = timestamp[11:16] if len(timestamp) >= 16 else ""

        # Container del messaggio
        row_frame = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        row_frame.pack(fill="x", pady=3)

        align_side = "right" if is_out else "left"
        bubble_color = "#0f766e" if is_out else "#27272a"
        text_color = "#ffffff"

        bubble = ctk.CTkFrame(row_frame, fg_color=bubble_color, corner_radius=12)
        bubble.pack(side=align_side, padx=6)

        msg_lbl = ctk.CTkLabel(
            bubble,
            text=text,
            font=ctk.CTkFont(size=13),
            text_color=text_color,
            wraplength=480,
            justify="left",
        )
        msg_lbl.pack(padx=12, pady=(8, 2), anchor="w")

        info_lbl = ctk.CTkLabel(
            bubble,
            text=f"{time_short} {'✓✓' if is_out else ''}",
            font=ctk.CTkFont(size=9),
            text_color="#a1a1aa",
        )
        info_lbl.pack(padx=12, pady=(0, 6), anchor="e")

    # =========================================================================
    # INVIO MESSAGGI CRITTOGRAFATI E2EE
    # =========================================================================
    def _send_current_message(self) -> None:
        if not self.selected_contact or self.selected_contact["status"] != "active":
            return

        text = self.txt_message.get().strip()
        if not text:
            return

        shared_key = self.selected_contact.get("shared_key")
        if not shared_key:
            messagebox.showerror("Errore Crittografico", "Chiave di sessione non disponibile per questa chat.")
            return

        recipient_guid = self.selected_contact["contact_guid"]
        sender_guid = self.current_identity["guid"]

        try:
            # 1. Cifratura locale del messaggio con AES-256-GCM
            ciphertext_b64, nonce_b64 = CipherEngine.encrypt_message(shared_key, text)

            # 2. Salvataggio locale in SQLite (cifrato a riposo con la Master Key)
            import uuid
            msg_id = str(uuid.uuid4())
            self.storage.save_message(
                message_id=msg_id,
                contact_guid=recipient_guid,
                is_outgoing=True,
                plaintext=text,
                status="sent",
            )

            # 3. Invio su Firebase Firestore (transito temporaneo)
            if self.firebase.is_connected():
                self.firebase.send_encrypted_message(
                    sender_id=sender_guid,
                    recipient_id=recipient_guid,
                    ciphertext_b64=ciphertext_b64,
                    nonce_b64=nonce_b64,
                    message_id=msg_id,
                )

            # Pulisci input e ricarica UI
            self.txt_message.delete(0, "end")
            self._load_chat_messages(recipient_guid)
            self.refresh_contacts_list()

        except Exception as e:
            messagebox.showerror("Errore Invio", f"Impossibile inviare il messaggio: {str(e)}")

    # =========================================================================
    # GESTIONE RICHIESTE CHAT & HANDSHAKE
    # =========================================================================
    def _show_new_chat_dialog(self) -> None:
        """Dialog per avviare un handshake con un nuovo utente tramite il suo GUID."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Nuova Richiesta di Chat E2EE")
        dialog.geometry("460x280")
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Invia Richiesta di Chat",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#2dd4bf",
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            dialog,
            text="Inserisci il GUID dell'utente con cui desideri stabilire una chat cifrata:",
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa",
        ).pack(pady=(0, 12))

        entry_guid = ctk.CTkEntry(dialog, placeholder_text="GUID Destinatario (es. user_...)")
        entry_guid.pack(fill="x", padx=24, pady=6)

        entry_nick = ctk.CTkEntry(dialog, placeholder_text="Soprannome per questo contatto (es. Bob)")
        entry_nick.pack(fill="x", padx=24, pady=6)

        def _submit():
            to_guid = entry_guid.get().strip()
            nickname = entry_nick.get().strip() or to_guid[:8]

            if not to_guid:
                messagebox.showwarning("Dato mancante", "Il GUID e' obbligatorio.", parent=dialog)
                return
            if to_guid == self.current_identity["guid"]:
                messagebox.showwarning("Non consentito", "Non puoi avviare una chat con te stesso.", parent=dialog)
                return

            try:
                # 1. Salva il contatto in locale come 'pending_sent'
                self.storage.save_or_update_contact(
                    contact_guid=to_guid,
                    nickname=nickname,
                    status="pending_sent",
                )

                # 2. Invia la richiesta su Firestore
                if self.firebase.is_connected():
                    self.firebase.send_chat_request(
                        from_guid=self.current_identity["guid"],
                        to_guid=to_guid,
                        sender_nickname=self.current_identity["nickname"],
                        sender_public_key=self.current_identity["public_key_b64"],
                    )

                dialog.destroy()
                self.refresh_contacts_list()
                messagebox.showinfo(
                    "Richiesta Inviata",
                    f"Richiesta inviata a {nickname}.\nQuando l'utente accettera', la chat verra' sbloccata automaticamente.",
                )
            except Exception as ex:
                messagebox.showerror("Errore", f"Errore durante l'invio della richiesta: {ex}", parent=dialog)

        btn_submit = ctk.CTkButton(
            dialog,
            text="Invia Richiesta Cifrata",
            fg_color="#0d9488",
            hover_color="#0f766e",
            command=_submit,
        )
        btn_submit.pack(pady=16)

    def _show_pending_requests_dialog(self) -> None:
        """Visualizza le richieste di chat ricevute in attesa di accettazione esplicita."""
        requests = self.storage.get_pending_requests()
        if not requests:
            messagebox.showinfo("Richieste Chat", "Nessuna richiesta di chat in sospeso.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Richieste di Chat Ricevute")
        dialog.geometry("500x380")
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Richieste di Chat in Sospeso",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ffffff",
        ).pack(pady=12)

        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.pack(fill="both", expand=True, padx=16, pady=8)

        for req in requests:
            card = ctk.CTkFrame(scroll, fg_color="#27272a", corner_radius=8)
            card.pack(fill="x", pady=4)

            info_lbl = ctk.CTkLabel(
                card,
                text=f"{req['sender_nickname']} ({req['from_guid']}) desidera chattare con te.",
                font=ctk.CTkFont(size=12),
                wraplength=320,
                justify="left",
            )
            info_lbl.pack(side="left", padx=10, pady=10)

            btn_box = ctk.CTkFrame(card, fg_color="transparent")
            btn_box.pack(side="right", padx=10, pady=10)

            btn_acc = ctk.CTkButton(
                btn_box,
                text="Accetta",
                width=65,
                height=28,
                fg_color="#0d9488",
                command=lambda r=req, d=dialog: self._accept_request(r, d),
            )
            btn_acc.pack(side="left", padx=2)

            btn_rej = ctk.CTkButton(
                btn_box,
                text="Rifiuta",
                width=65,
                height=28,
                fg_color="#ef4444",
                hover_color="#dc2626",
                command=lambda r=req, d=dialog: self._reject_request(r, d),
            )
            btn_rej.pack(side="left", padx=2)

    def _accept_request(self, req: Dict[str, Any], dialog_to_close: ctk.CTkToplevel) -> None:
        """
        L'utente accetta esplicitamente la richiesta:
        1. Calcola la chiave di sessione condivisa tramite Diffie-Hellman (X25519) + HKDF
        2. Salva il contatto e la chiave di sessione AES-256 nel DB SQLite locale
        3. Invia la propria chiave pubblica di risposta su Firestore
        4. Rimuove la richiesta pendente
        """
        try:
            from_guid = req["from_guid"]
            sender_pub = req["sender_public_key"]
            sender_nick = req["sender_nickname"]
            req_id = req["request_id"]

            # 1. Key Agreement Diffie-Hellman
            shared_key = CipherEngine.compute_shared_key(
                my_private_key_b64=self.current_identity["private_key_b64"],
                peer_public_key_b64=sender_pub,
            )

            # 2. Salva contatto con stato 'active' e chiave di sessione
            self.storage.save_or_update_contact(
                contact_guid=from_guid,
                nickname=sender_nick,
                public_key_b64=sender_pub,
                shared_key=shared_key,
                status="active",
            )

            # 3. Aggiorna Firestore con la chiave pubblica locale
            if self.firebase.is_connected():
                self.firebase.accept_chat_request(
                    request_id=req_id,
                    recipient_public_key=self.current_identity["public_key_b64"],
                )

            # 4. Rimuovi dai pendenti locali
            self.storage.remove_pending_request(req_id)

            dialog_to_close.destroy()
            self.refresh_contacts_list()
            messagebox.showinfo(
                "Handshake Completato",
                f"Hai accettato la chat con {sender_nick}.\nLa chiave di sessione AES-256-GCM e' stata negoziata con successo!",
            )
        except Exception as ex:
            messagebox.showerror("Errore Handshake", f"Impossibile accettare la richiesta: {ex}")

    def _reject_request(self, req: Dict[str, Any], dialog_to_close: ctk.CTkToplevel) -> None:
        try:
            req_id = req["request_id"]
            if self.firebase.is_connected():
                self.firebase.reject_chat_request(req_id)
            self.storage.remove_pending_request(req_id)
            dialog_to_close.destroy()
            self.refresh_contacts_list()
        except Exception as ex:
            messagebox.showerror("Errore", f"Errore rifiuto richiesta: {ex}")

    # =========================================================================
    # LISTENER DI RETE FIREBASE (Ricezione Messaggi & Handshake Updates)
    # =========================================================================
    def _start_network_listeners(self) -> None:
        """Inizializza i listener Firestore in background per messaggi e handshake."""
        if not self.firebase.is_connected() or not self.current_identity:
            return

        my_guid = self.current_identity["guid"]

        # 1. Listener Messaggi (Acknowledge & Delete)
        self.firebase.listen_and_consume_messages(
            my_guid=my_guid,
            on_message_received=self._on_message_received_from_cloud,
        )

        # 2. Listener Richieste Chat in Arrivo
        self.firebase.listen_incoming_chat_requests(
            my_guid=my_guid,
            on_request_received=self._on_chat_request_received_from_cloud,
        )

        # 3. Listener Aggiornamento Richieste Inviate (Accettazione da parte di Bob)
        self.firebase.listen_outgoing_chat_requests(
            my_guid=my_guid,
            on_request_updated=self._on_outgoing_request_updated_from_cloud,
        )

    def _on_message_received_from_cloud(self, raw_msg: Dict[str, Any]) -> None:
        """
        Callback invocato al download del messaggio cifrato dal cloud.
        Sequenza vincolante:
        1. Scarica il messaggio cifrato (eseguito in FirebaseClient).
        2. Salva nel database SQLite locale sul PC (decifrandolo con la shared_key del contatto).
        3. ACK a Firebase cancellando il documento (eseguito in FirebaseClient subito dopo questa funzione).
        """
        sender_id = raw_msg.get("sender_id")
        ciphertext_b64 = raw_msg.get("ciphertext")
        nonce_b64 = raw_msg.get("nonce")
        msg_id = raw_msg.get("message_id")

        if not sender_id or not ciphertext_b64 or not nonce_b64:
            return

        contact = self.storage.get_contact(sender_id)
        if not contact or not contact.get("shared_key"):
            return

        try:
            # Decifratura AES-256-GCM
            plaintext = CipherEngine.decrypt_message(
                shared_key=contact["shared_key"],
                ciphertext_b64=ciphertext_b64,
                nonce_b64=nonce_b64,
            )

            # Salvataggio nel database locale SQLite (cifrato a riposo con la Master Key)
            saved = self.storage.save_message(
                message_id=msg_id,
                contact_guid=sender_id,
                is_outgoing=False,
                plaintext=plaintext,
                status="received",
            )

            if saved:
                # Notifica nativa Windows
                sender_name = contact.get("nickname", "Contatto")
                self.notifier.show_notification(
                    title=f"🔒 {sender_name}",
                    message="Nuovo messaggio cifrato ricevuto.",
                )

                # Aggiornamento UI nel thread principale di CustomTkinter
                self.after(0, lambda: self._handle_new_message_ui_update(sender_id))

        except Exception as ex:
            print(f"[Ricezione] Errore decifratura messaggio: {ex}")

    def _handle_new_message_ui_update(self, sender_id: str) -> None:
        self.refresh_contacts_list()
        if self.selected_contact and self.selected_contact["contact_guid"] == sender_id:
            self._load_chat_messages(sender_id)
            self.storage.mark_chat_read(sender_id)

    def _on_chat_request_received_from_cloud(self, req_data: Dict[str, Any]) -> None:
        """Rilevata una nuova richiesta di chat indirizzata a questo PC."""
        req_id = req_data.get("request_id")
        from_guid = req_data.get("from_guid")
        sender_nick = req_data.get("sender_nickname", "Utente Sconosciuto")
        sender_pub = req_data.get("sender_public_key")
        created_at = str(req_data.get("created_at") or "")

        if not req_id or not from_guid or not sender_pub:
            return

        self.storage.save_pending_request(
            request_id=req_id,
            from_guid=from_guid,
            sender_nickname=sender_nick,
            sender_public_key=sender_pub,
            created_at=created_at,
        )

        self.notifier.show_notification(
            title="Richiesta di Chat E2EE",
            message=f"{sender_nick} vuole avviare una chat protetta con te.",
        )

        self.after(0, self.refresh_contacts_list)

    def _on_outgoing_request_updated_from_cloud(self, req_data: Dict[str, Any]) -> None:
        """
        L'Utente B ha accettato la nostra richiesta:
        Estraiamo la sua chiave pubblica, calcoliamo la chiave di sessione AES-256 e sblocchiamo la chat!
        """
        status = req_data.get("status")
        to_guid = req_data.get("to_guid")
        recip_pub = req_data.get("recipient_public_key")

        if status == "accepted" and to_guid and recip_pub:
            contact = self.storage.get_contact(to_guid)
            if contact and contact["status"] != "active":
                # Calcola Shared Key
                shared_key = CipherEngine.compute_shared_key(
                    my_private_key_b64=self.current_identity["private_key_b64"],
                    peer_public_key_b64=recip_pub,
                )

                self.storage.save_or_update_contact(
                    contact_guid=to_guid,
                    nickname=contact["nickname"],
                    public_key_b64=recip_pub,
                    shared_key=shared_key,
                    status="active",
                )

                # Cancella il documento di richiesta ormai concluso (pulizia serverless)
                if self.firebase.is_connected():
                    doc_id = req_data.get("doc_id") or f"{self.current_identity['guid']}_{to_guid}"
                    try:
                        self.firebase.db.collection("chat_requests").document(doc_id).delete()
                    except Exception:
                        pass

                self.notifier.show_notification(
                    title="Richiesta Accettata!",
                    message=f"{contact['nickname']} ha accettato la chat. La cifratura E2EE e' attiva!",
                )

                self.after(0, self.refresh_contacts_list)
                if self.selected_contact and self.selected_contact["contact_guid"] == to_guid:
                    self.after(0, lambda: self._select_contact(contact))

    # =========================================================================
    # FINESTRA DI CONFIGURAZIONE FIREBASE
    # =========================================================================
    def _show_firebase_config_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Configurazione Firebase Firestore")
        dialog.geometry("520x300")
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Connessione Firebase Firestore",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#2dd4bf",
        ).pack(pady=(16, 6))

        ctk.CTkLabel(
            dialog,
            text="Seleziona il file serviceAccountKey.json generato dalla Firebase Console:\n(Progetto > Impostazioni > Account di servizio > Genera nuova chiave privata)",
            font=ctk.CTkFont(size=11),
            text_color="#a1a1aa",
            justify="center",
        ).pack(pady=(0, 14))

        path_var = tk.StringVar(value=self.firebase.credentials_path or "")
        entry_path = ctk.CTkEntry(dialog, textvariable=path_var, width=420)
        entry_path.pack(pady=6)

        def _browse_file():
            filename = filedialog.askopenfilename(
                title="Seleziona serviceAccountKey.json",
                filetypes=[("JSON files", "*.json"), ("Tutti i file", "*.*")],
                parent=dialog,
            )
            if filename:
                path_var.set(filename)

        btn_browse = ctk.CTkButton(dialog, text="Sfoglia file...", width=120, command=_browse_file)
        btn_browse.pack(pady=4)

        def _save_and_connect():
            p = path_var.get().strip()
            if not p or not os.path.exists(p):
                messagebox.showerror("File non trovato", "Specificare un file JSON esistente.", parent=dialog)
                return
            try:
                # Auto-rileva il database appropriato dal progetto Google Cloud
                self.firebase.initialize(p)
                db_name = self.firebase.database_id or "(default)"
                self.storage.set_setting("firestore_database_id", db_name)
                self.lbl_firebase_status.configure(
                    text=f"🟢 Firebase ({db_name})", text_color="#34d399"
                )
                self._start_network_listeners()
                dialog.destroy()
                messagebox.showinfo(
                    "Connesso",
                    f"Connessione a Firestore stabilita con successo!\nDatabase: '{db_name}'",
                )
            except Exception as e:
                messagebox.showerror("Errore Connessione", str(e), parent=dialog)

        btn_connect = ctk.CTkButton(
            dialog,
            text="Collega e Avvia Listener",
            fg_color="#0d9488",
            hover_color="#0f766e",
            command=_save_and_connect,
        )
        btn_connect.pack(pady=16)

    # =========================================================================
    # GESTIONE SYSTEM TRAY E CHIUSURA
    # =========================================================================
    def hide_to_tray(self) -> None:
        """Minimizza l'applicazione nella System Tray invece di chiuderla."""
        self.withdraw()
        self.notifier.show_notification(
            title="SecureChat E2EE",
            message="L'applicazione e' attiva in background vicino all'orologio di Windows.",
        )

    def restore_from_tray(self) -> None:
        """Ripristina la finestra principale dalla System Tray."""
        self.after(0, self._do_restore)

    def _do_restore(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def exit_application(self) -> None:
        """Chiusura definitiva dell'applicazione."""
        self._is_closing = True
        if self.firebase:
            self.firebase.stop_all_listeners()
        self.destroy()

    def _copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        messagebox.showinfo("Copiato", "GUID copiato negli appunti!")
