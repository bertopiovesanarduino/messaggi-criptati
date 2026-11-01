"""
Modulo FirebaseClient per Firestore Serverless Routing
======================================================
Gestisce:
1. Handshake e scambio chiavi asimmetriche (collection 'chat_requests')
2. Coda temporanea dei messaggi (collection 'messages')
3. Pattern 'Acknowledge & Delete' per cancellazione immediata dal cloud
4. Impostazione del campo TTL (5 giorni) come fallback
"""

import os
import json
import uuid
import datetime
import threading
from typing import Optional, Callable, Dict, Any, List

FIREBASE_AVAILABLE = False
FIREBASE_IMPORT_ERROR = None

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except Exception as _err:
    FIREBASE_IMPORT_ERROR = str(_err)


class FirebaseClient:
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        database_id: Optional[str] = None,
    ):
        self.credentials_path = credentials_path
        self.database_id = database_id
        self.db = None
        self._is_initialized = False
        self._active_listeners: List[Any] = []
        self._lock = threading.Lock()

        if credentials_path and os.path.exists(credentials_path):
            try:
                self.initialize(credentials_path, database_id=database_id)
            except Exception as e:
                print(f"[FirebaseClient] Inizializzazione automatica non riuscita: {e}")

    @staticmethod
    def get_available_databases(credentials_path: str) -> List[str]:
        """
        Interroga Google Cloud per elencare i database Firestore del progetto.
        Ritorna una lista dei nomi di database (es. ['(default)', 'banane']).
        """
        if not credentials_path or not os.path.exists(credentials_path):
            return []
        try:
            with open(credentials_path, "r", encoding="utf-8") as f:
                key_data = json.load(f)
            project_id = key_data.get("project_id")
            if not project_id:
                return []

            from google.cloud import firestore_admin_v1
            from google.oauth2 import service_account

            admin_cred = service_account.Credentials.from_service_account_file(credentials_path)
            admin_client = firestore_admin_v1.FirestoreAdminClient(credentials=admin_cred)
            resp = admin_client.list_databases(parent=f"projects/{project_id}")
            return [d.name.split("/")[-1] for d in resp.databases]
        except Exception as ex:
            print(f"[FirebaseClient] Errore elenco database Firestore: {ex}")
            return []

    def _resolve_database_id(self, credentials_path: str, requested_db_id: Optional[str]) -> Optional[str]:
        """
        Determina il database ID effettivo da usare:
        1. Se specificato esplicitamente e non è 'auto' o vuoto, usa quello.
        2. Altrimenti, esamina i database esistenti nel progetto Google Cloud:
           - Se '(default)' esiste, usa '(default)'.
           - Se '(default)' non esiste ma c'è un altro database (es. 'banane'), sceglie quello!
        """
        if requested_db_id and requested_db_id.strip() and requested_db_id.strip().lower() != "auto":
            clean_id = requested_db_id.strip()
            return clean_id if clean_id != "(default)" else None

        dbs = self.get_available_databases(credentials_path)
        if "(default)" in dbs:
            return None
        elif dbs:
            return dbs[0]
        return None

    def initialize(self, credentials_path: str, database_id: Optional[str] = None) -> bool:
        """Inizializza l'app Firebase Admin con il database Firestore appropriato."""
        if not FIREBASE_AVAILABLE:
            detail = f": {FIREBASE_IMPORT_ERROR}" if FIREBASE_IMPORT_ERROR else ""
            raise RuntimeError(f"Libreria 'firebase-admin' non disponibile{detail}. Installa con: pip install firebase-admin")

        self.stop_all_listeners()

        with self._lock:
            try:
                # Evita inizializzazioni multiple di firebase_admin
                if not firebase_admin._apps:
                    cred = credentials.Certificate(credentials_path)
                    firebase_admin.initialize_app(cred)

                resolved_db = self._resolve_database_id(credentials_path, database_id)

                if resolved_db:
                    self.db = firestore.client(database_id=resolved_db)
                    self.database_id = resolved_db
                else:
                    self.db = firestore.client()
                    self.database_id = "(default)"

                # Verifica connettività effettiva: stream di test rapido
                list(self.db.collection("chat_requests").limit(1).stream(timeout=7))

                self._is_initialized = True
                self.credentials_path = credentials_path
                print(f"[FirebaseClient] Connessione riuscita a Firestore (Database: '{self.database_id}')")
                return True
            except Exception as e:
                self._is_initialized = False
                self.db = None
                raise RuntimeError(f"Errore inizializzazione Firebase (database '{self.database_id or '(default)'}'): {str(e)}")

    def is_connected(self) -> bool:
        return self._is_initialized and self.db is not None

    # =========================================================================
    # 1. IDENTITA' E HANDSHAKE (Collection 'chat_requests')
    # =========================================================================
    def send_chat_request(
        self,
        from_guid: str,
        to_guid: str,
        sender_nickname: str,
        sender_public_key: str,
    ) -> str:
        """
        Invia una richiesta di handshake all'Utente B su Firestore.
        """
        if not self.is_connected():
            raise ConnectionError("Firebase Firestore non e' connesso.")

        request_id = f"{from_guid}_{to_guid}"
        req_ref = self.db.collection("chat_requests").document(request_id)

        req_ref.set({
            "request_id": request_id,
            "from_guid": from_guid,
            "to_guid": to_guid,
            "sender_nickname": sender_nickname,
            "sender_public_key": sender_public_key,
            "recipient_public_key": None,
            "status": "pending",  # 'pending', 'accepted', 'rejected'
            "created_at": firestore.SERVER_TIMESTAMP,
            "ttl_date": datetime.datetime.utcnow() + datetime.timedelta(days=5),
        })
        return request_id

    def accept_chat_request(self, request_id: str, recipient_public_key: str) -> None:
        """
        L'Utente B accetta esplicitamente la richiesta di chat, inviando la propria chiave pubblica.
        """
        if not self.is_connected():
            raise ConnectionError("Firebase Firestore non e' connesso.")

        req_ref = self.db.collection("chat_requests").document(request_id)
        req_ref.update({
            "recipient_public_key": recipient_public_key,
            "status": "accepted",
            "accepted_at": firestore.SERVER_TIMESTAMP,
        })

    def reject_chat_request(self, request_id: str) -> None:
        """Rifiuta ed elimina la richiesta di chat."""
        if not self.is_connected():
            raise ConnectionError("Firebase Firestore non e' connesso.")

        self.db.collection("chat_requests").document(request_id).delete()

    def listen_incoming_chat_requests(
        self, my_guid: str, on_request_received: Callable[[Dict[str, Any]], None]
    ) -> Any:
        """
        Ascolta in tempo reale le nuove richieste di chat dirette a 'my_guid'.
        """
        if not self.is_connected():
            return None

        query = self.db.collection("chat_requests").where("to_guid", "==", my_guid).where("status", "==", "pending")

        def _on_snapshot(docs, changes, read_time):
            for doc in docs:
                data = doc.to_dict()
                if data:
                    data["doc_id"] = doc.id
                    on_request_received(data)

        watch = query.on_snapshot(_on_snapshot)
        with self._lock:
            self._active_listeners.append(watch)
        return watch

    def listen_outgoing_chat_requests(
        self, my_guid: str, on_request_updated: Callable[[Dict[str, Any]], None]
    ) -> Any:
        """
        Ascolta gli aggiornamenti alle richieste inviate da 'my_guid' (per rilevare l'accettazione di B).
        """
        if not self.is_connected():
            return None

        query = self.db.collection("chat_requests").where("from_guid", "==", my_guid)

        def _on_snapshot(docs, changes, read_time):
            for doc in docs:
                data = doc.to_dict()
                if data:
                    data["doc_id"] = doc.id
                    on_request_updated(data)

        watch = query.on_snapshot(_on_snapshot)
        with self._lock:
            self._active_listeners.append(watch)
        return watch

    # =========================================================================
    # 2. ROUTING DEI MESSAGGI (Acknowledge & Delete)
    # =========================================================================
    def send_encrypted_message(
        self,
        sender_id: str,
        recipient_id: str,
        ciphertext_b64: str,
        nonce_b64: str,
        message_id: Optional[str] = None,
    ) -> str:
        """
        Invia un pacchetto cifrato su Firestore nella collection 'messages'.
        Imposta il campo 'ttl_date' a 5 giorni per la policy TTL automatica.
        """
        if not self.is_connected():
            raise ConnectionError("Firebase Firestore non e' connesso.")

        msg_id = message_id or str(uuid.uuid4())
        msg_ref = self.db.collection("messages").document(msg_id)

        # Calcolo scadenza TTL a 5 giorni
        ttl_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=5)

        msg_ref.set({
            "message_id": msg_id,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "ciphertext": ciphertext_b64,
            "nonce": nonce_b64,
            "created_at": firestore.SERVER_TIMESTAMP,
            "ttl_date": ttl_expiry,
        })
        return msg_id

    def listen_and_consume_messages(
        self,
        my_guid: str,
        on_message_received: Callable[[Dict[str, Any]], None],
    ) -> Any:
        """
        Ascolta i messaggi cifrati in arrivo per 'my_guid'.
        Applica tassativamente il pattern 'Acknowledge & Delete':
        1. Scarica il messaggio cifrato.
        2. Chiama la callback locale (salvataggio nel DB SQLite del PC).
        3. Cancella IMMEDIATAMENTE il documento da Firestore (ACK).
        """
        if not self.is_connected():
            return None

        query = self.db.collection("messages").where("recipient_id", "==", my_guid)

        def _on_snapshot(docs, changes, read_time):
            for doc in docs:
                try:
                    data = doc.to_dict()
                    if not data:
                        continue

                    # 1. Dati del messaggio cifrato
                    data["doc_id"] = doc.id

                    # 2. Notifica il client locale che salvera' su SQLite
                    on_message_received(data)

                    # 3. ACK & DELETE immediato: Rimuove il documento dal cloud
                    doc.reference.delete()
                except Exception as ex:
                    # In caso di errore durante l'elaborazione, il documento resta per retry
                    print(f"[FirebaseClient] Errore elaborazione messaggio: {ex}")

        watch = query.on_snapshot(_on_snapshot)
        with self._lock:
            self._active_listeners.append(watch)
        return watch

    def stop_all_listeners(self) -> None:
        """Chiude tutti i listener attivi di Firestore."""
        with self._lock:
            for listener in self._active_listeners:
                try:
                    listener.unsubscribe()
                except Exception:
                    pass
            self._active_listeners.clear()
