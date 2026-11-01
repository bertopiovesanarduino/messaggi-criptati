"""
Modulo LocalStorage (SQLite Cifrato a Riposo)
==============================================
Gestisce la persistenza locale sul PC Windows dell'utente in `%APPDATA%/SecureChatE2EE/`.
Tutti i dati sensibili (chiavi private, chiavi simmetriche di sessione,
e contenuti dei messaggi) sono cifrati con AES-256-GCM tramite una Master Key
protetta con Windows DPAPI (CryptProtectData).
"""

import os
import sqlite3
import uuid
import datetime
import base64
from typing import Optional, Dict, List, Any

from app.crypto.cipher_engine import CipherEngine


class LocalStorage:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            data_dir = os.path.join(appdata, "SecureChatE2EE")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "chat_vault.db")
            self.key_path = os.path.join(data_dir, "vault.key")
        else:
            self.db_path = db_path
            self.key_path = os.path.splitext(db_path)[0] + ".key"

        # Inizializza Master Key locale protetta da DPAPI
        self.master_key = CipherEngine.get_or_create_master_key(self.key_path)

        # Inizializza le tabelle SQLite
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self) -> None:
        """Crea lo schema del database se non esistente."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Tabella Identita' Locale Utente
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS identity (
                    guid TEXT PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    public_key_b64 TEXT NOT NULL,
                    encrypted_private_key TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Tabella Contatti & Handshake
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    contact_guid TEXT PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    public_key_b64 TEXT,
                    encrypted_shared_key TEXT,
                    status TEXT NOT NULL, -- 'pending_sent', 'pending_received', 'active', 'rejected'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Tabella Storico Messaggi
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    contact_guid TEXT NOT NULL,
                    is_outgoing INTEGER NOT NULL, -- 1 = inviato da me, 0 = ricevuto
                    encrypted_content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL, -- 'sent', 'received', 'read'
                    FOREIGN KEY (contact_guid) REFERENCES contacts(contact_guid)
                );
            """)

            # Tabella Richieste Ricevute (in attesa di accettazione)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_requests (
                    request_id TEXT PRIMARY KEY,
                    from_guid TEXT NOT NULL,
                    sender_nickname TEXT NOT NULL,
                    sender_public_key TEXT NOT NULL,
                    status TEXT NOT NULL, -- 'pending', 'accepted', 'rejected'
                    created_at TEXT NOT NULL
                );
            """)

            # Tabella Impostazioni Applicazione (Key-Value)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            conn.commit()

    # =========================================================================
    # Gestione Impostazioni Generiche
    # =========================================================================
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Recupera un'impostazione salvata localmente nel DB."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Salva o aggiorna un'impostazione nel DB locale."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()

    # =========================================================================
    # Gestione Identita'
    # =========================================================================
    def get_identity(self) -> Optional[Dict[str, Any]]:
        """Recupera l'identita' salvata nel PC, se presente."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guid, nickname, public_key_b64, encrypted_private_key FROM identity LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None

            private_key_b64 = CipherEngine.decrypt_local_field(self.master_key, row["encrypted_private_key"])
            return {
                "guid": row["guid"],
                "nickname": row["nickname"],
                "public_key_b64": row["public_key_b64"],
                "private_key_b64": private_key_b64,
            }

    def create_identity(self, nickname: str) -> Dict[str, Any]:
        """Genera un nuovo GUID e una coppia di chiavi X25519 al primo avvio."""
        existing = self.get_identity()
        if existing:
            return existing

        guid = f"user_{uuid.uuid4().hex[:12]}"
        priv_b64, pub_b64 = CipherEngine.generate_key_pair()
        enc_priv = CipherEngine.encrypt_local_field(self.master_key, priv_b64)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO identity (guid, nickname, public_key_b64, encrypted_private_key)
                VALUES (?, ?, ?, ?)
                """,
                (guid, nickname, pub_b64, enc_priv),
            )
            conn.commit()

        return {
            "guid": guid,
            "nickname": nickname,
            "public_key_b64": pub_b64,
            "private_key_b64": priv_b64,
        }

    # =========================================================================
    # Gestione Contatti & Sessioni Cifrate
    # =========================================================================
    def save_or_update_contact(
        self,
        contact_guid: str,
        nickname: str,
        public_key_b64: Optional[str] = None,
        shared_key: Optional[bytes] = None,
        status: str = "pending",
    ) -> None:
        """Salva o aggiorna un contatto e la sua chiave di sessione AES-256."""
        enc_shared = ""
        if shared_key:
            shared_b64 = base64.b64encode(shared_key).decode("utf-8")
            enc_shared = CipherEngine.encrypt_local_field(self.master_key, shared_b64)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT contact_guid, encrypted_shared_key, public_key_b64 FROM contacts WHERE contact_guid = ?", (contact_guid,))
            existing = cursor.fetchone()

            if existing:
                # Mantieni chiavi precedenti se non fornite
                final_enc_shared = enc_shared if enc_shared else existing["encrypted_shared_key"]
                final_pub = public_key_b64 if public_key_b64 else existing["public_key_b64"]
                cursor.execute(
                    """
                    UPDATE contacts
                    SET nickname = ?, public_key_b64 = ?, encrypted_shared_key = ?, status = ?
                    WHERE contact_guid = ?
                    """,
                    (nickname, final_pub, final_enc_shared, status, contact_guid),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO contacts (contact_guid, nickname, public_key_b64, encrypted_shared_key, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (contact_guid, nickname, public_key_b64 or "", enc_shared, status),
                )
            conn.commit()

    def get_contacts(self) -> List[Dict[str, Any]]:
        """Restituisce l'elenco di tutti i contatti con l'ultimo messaggio e timestamp."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.contact_guid, c.nickname, c.public_key_b64, c.encrypted_shared_key, c.status,
                       (SELECT encrypted_content FROM messages WHERE contact_guid = c.contact_guid ORDER BY timestamp DESC LIMIT 1) as last_msg_enc,
                       (SELECT timestamp FROM messages WHERE contact_guid = c.contact_guid ORDER BY timestamp DESC LIMIT 1) as last_msg_time,
                       (SELECT COUNT(*) FROM messages WHERE contact_guid = c.contact_guid AND is_outgoing = 0 AND status = 'received') as unread_count
                FROM contacts c
                ORDER BY CASE WHEN last_msg_time IS NOT NULL THEN last_msg_time ELSE c.created_at END DESC
            """)
            rows = cursor.fetchall()

            contacts = []
            for r in rows:
                shared_key = None
                if r["encrypted_shared_key"]:
                    dec = CipherEngine.decrypt_local_field(self.master_key, r["encrypted_shared_key"])
                    if dec and not dec.startswith("[Errore"):
                        shared_key = base64.b64decode(dec)

                last_msg = ""
                if r["last_msg_enc"]:
                    last_msg = CipherEngine.decrypt_local_field(self.master_key, r["last_msg_enc"])

                contacts.append({
                    "contact_guid": r["contact_guid"],
                    "nickname": r["nickname"],
                    "public_key_b64": r["public_key_b64"],
                    "shared_key": shared_key,
                    "status": r["status"],
                    "last_message": last_msg,
                    "last_timestamp": r["last_msg_time"] or "",
                    "unread_count": r["unread_count"] or 0,
                })
            return contacts

    def get_contact(self, contact_guid: str) -> Optional[Dict[str, Any]]:
        """Restituisce le informazioni di un singolo contatto e la sua shared_key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE contact_guid = ?", (contact_guid,))
            row = cursor.fetchone()
            if not row:
                return None

            shared_key = None
            if row["encrypted_shared_key"]:
                dec = CipherEngine.decrypt_local_field(self.master_key, row["encrypted_shared_key"])
                if dec and not dec.startswith("[Errore"):
                    shared_key = base64.b64decode(dec)

            return {
                "contact_guid": row["contact_guid"],
                "nickname": row["nickname"],
                "public_key_b64": row["public_key_b64"],
                "shared_key": shared_key,
                "status": row["status"],
            }

    # =========================================================================
    # Gestione Messaggi Locali
    # =========================================================================
    def save_message(
        self,
        message_id: str,
        contact_guid: str,
        is_outgoing: bool,
        plaintext: str,
        timestamp: Optional[str] = None,
        status: str = "delivered",
    ) -> bool:
        """Salva un messaggio cifrandolo a riposo nel database locale."""
        if timestamp is None:
            timestamp = datetime.datetime.now().isoformat()

        enc_content = CipherEngine.encrypt_local_field(self.master_key, plaintext)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Ignora duplicati se il messaggio e' gia' stato archiviato
            cursor.execute("SELECT message_id FROM messages WHERE message_id = ?", (message_id,))
            if cursor.fetchone():
                return False

            cursor.execute(
                """
                INSERT INTO messages (message_id, contact_guid, is_outgoing, encrypted_content, timestamp, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, contact_guid, 1 if is_outgoing else 0, enc_content, timestamp, status),
            )
            conn.commit()
            return True

    def get_messages(self, contact_guid: str) -> List[Dict[str, Any]]:
        """Restituisce lo storico messaggi decifrati per una determinata chat."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT message_id, is_outgoing, encrypted_content, timestamp, status
                FROM messages
                WHERE contact_guid = ?
                ORDER BY timestamp ASC
                """,
                (contact_guid,),
            )
            rows = cursor.fetchall()

            messages = []
            for r in rows:
                decrypted_text = CipherEngine.decrypt_local_field(self.master_key, r["encrypted_content"])
                messages.append({
                    "message_id": r["message_id"],
                    "is_outgoing": bool(r["is_outgoing"]),
                    "text": decrypted_text,
                    "timestamp": r["timestamp"],
                    "status": r["status"],
                })
            return messages

    def mark_chat_read(self, contact_guid: str) -> None:
        """Segna tutti i messaggi ricevuti del contatto come letti."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE messages SET status = 'read' WHERE contact_guid = ? AND is_outgoing = 0",
                (contact_guid,),
            )
            conn.commit()

    # =========================================================================
    # Gestione Richieste Chat Pending (Handshake)
    # =========================================================================
    def save_pending_request(
        self, request_id: str, from_guid: str, sender_nickname: str, sender_public_key: str, created_at: str
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pending_requests (request_id, from_guid, sender_nickname, sender_public_key, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (request_id, from_guid, sender_nickname, sender_public_key, created_at),
            )
            conn.commit()

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_requests WHERE status = 'pending' ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def remove_pending_request(self, request_id: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_requests WHERE request_id = ?", (request_id,))
            conn.commit()
