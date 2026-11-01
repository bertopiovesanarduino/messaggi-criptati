"""
Modulo di Crittografia End-to-End (E2EE)
=========================================
Algoritmi utilizzati:
- Scambio di chiavi asimmetriche: X25519 (Elliptic Curve Diffie-Hellman su Curve25519)
- Key Derivation Function: HKDF con HMAC-SHA256 (RFC 5869)
- Cifratura autenticata simmetrica: AES-256-GCM (Galois/Counter Mode con Nonce da 96 bit e Tag da 128 bit)
- Protezione dati locali a riposo: DPAPI Windows (CryptProtectData) + AES-256-GCM
"""

import os
import base64
import ctypes
from ctypes import wintypes
from typing import Tuple, Optional

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


# =====================================================================
# Strutture Win32 per DPAPI (Protezione della Master Key su Windows)
# =====================================================================
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _win32_protect_data(data: bytes, entropy: bytes = b"E2EE_Desktop_Salt") -> bytes:
    """Cifra i byte usando Windows DPAPI (CryptProtectData)."""
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
        entropy_blob = DATA_BLOB(len(entropy), ctypes.cast(ctypes.create_string_buffer(entropy), ctypes.POINTER(ctypes.c_byte)))
        data_out = DATA_BLOB()

        flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
        if not crypt32.CryptProtectData(
            ctypes.byref(data_in), None, ctypes.byref(entropy_blob), None, None, flags, ctypes.byref(data_out)
        ):
            raise ctypes.WinError()

        encrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
        kernel32.LocalFree(data_out.pbData)
        return encrypted
    except Exception:
        # Fallback trasparente se DPAPI non e' disponibile nell'ambiente corrente
        return b"PLAIN:" + data


def _win32_unprotect_data(encrypted_data: bytes, entropy: bytes = b"E2EE_Desktop_Salt") -> bytes:
    """Decifra i byte usando Windows DPAPI (CryptUnprotectData)."""
    if encrypted_data.startswith(b"PLAIN:"):
        return encrypted_data[6:]
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_in = DATA_BLOB(len(encrypted_data), ctypes.cast(ctypes.create_string_buffer(encrypted_data), ctypes.POINTER(ctypes.c_byte)))
        entropy_blob = DATA_BLOB(len(entropy), ctypes.cast(ctypes.create_string_buffer(entropy), ctypes.POINTER(ctypes.c_byte)))
        data_out = DATA_BLOB()

        flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
        if not crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, ctypes.byref(entropy_blob), None, None, flags, ctypes.byref(data_out)
        ):
            raise ctypes.WinError()

        decrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
        kernel32.LocalFree(data_out.pbData)
        return decrypted
    except Exception:
        return encrypted_data


class CipherEngine:
    """
    Motore crittografico per gestione chiavi, handshake ed E2EE AES-256-GCM.
    """

    @staticmethod
    def generate_key_pair() -> Tuple[str, str]:
        """
        Genera una coppia di chiavi X25519 (Curve25519).
        Ritorna:
            Tuple[str, str]: (private_key_b64, public_key_b64)
        """
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key()

        priv_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        return (
            base64.b64encode(priv_bytes).decode("utf-8"),
            base64.b64encode(pub_bytes).decode("utf-8"),
        )

    @staticmethod
    def compute_shared_key(my_private_key_b64: str, peer_public_key_b64: str) -> bytes:
        """
        Esegue il Key Agreement Diffie-Hellman tra la chiave privata locale
        e la chiave pubblica remota ricevuta nell'handshake, derivando una
        chiave simmetrica a 256 bit tramite HKDF-SHA256.
        """
        priv_bytes = base64.b64decode(my_private_key_b64)
        pub_bytes = base64.b64decode(peer_public_key_b64)

        my_private_key = x25519.X25519PrivateKey.from_private_bytes(priv_bytes)
        peer_public_key = x25519.X25519PublicKey.from_public_bytes(pub_bytes)

        # 1. Diffie-Hellman Shared Secret (32 bytes)
        raw_shared_secret = my_private_key.exchange(peer_public_key)

        # 2. Key Derivation Function (HKDF-SHA256) per conformita' crittografica
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bit per AES-256
            salt=b"E2EE_SECURE_CHAT_V1_SALT",
            info=b"AES_256_GCM_SESSION_KEY",
        )
        shared_aes_key = hkdf.derive(raw_shared_secret)
        return shared_aes_key

    @staticmethod
    def encrypt_message(shared_key: bytes, plaintext: str) -> Tuple[str, str]:
        """
        Cifra una stringa usando AES-256-GCM.
        Genera un Nonce crittografico a 96 bit (12 byte) univoco per ogni messaggio.

        Parametri:
            shared_key (bytes): Chiave simmetrica a 32 bytes (256 bit).
            plaintext (str): Testo in chiaro del messaggio.

        Ritorna:
            Tuple[str, str]: (ciphertext_base64, nonce_base64)
        """
        nonce = os.urandom(12)  # 96-bit nonce come raccomandato da NIST SP 800-38D
        aesgcm = AESGCM(shared_key)
        
        # In AESGCM di cryptography, il tag di autenticazione a 16 byte viene automaticamente
        # calcolato e appeso alla fine del ciphertext.
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)

        return (
            base64.b64encode(ciphertext).decode("utf-8"),
            base64.b64encode(nonce).decode("utf-8"),
        )

    @staticmethod
    def decrypt_message(shared_key: bytes, ciphertext_b64: str, nonce_b64: str) -> str:
        """
        Decifra un messaggio AES-256-GCM verificandone l'integrita' e l'autenticita'.
        Lancia InvalidTag se il messaggio o il tag e' stato alterato.
        """
        ciphertext = base64.b64decode(ciphertext_b64)
        nonce = base64.b64decode(nonce_b64)

        aesgcm = AESGCM(shared_key)
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
        return decrypted_bytes.decode("utf-8")

    # =========================================================================
    # Protezione del database locale (Data-at-Rest)
    # =========================================================================
    @classmethod
    def get_or_create_master_key(cls, key_file_path: str) -> bytes:
        """
        Recupera o genera una Master Key locale per cifrare i dati a riposo in SQLite.
        La Master Key viene protetta sul disco tramite Windows DPAPI.
        """
        os.makedirs(os.path.dirname(os.path.abspath(key_file_path)), exist_ok=True)
        if os.path.exists(key_file_path):
            with open(key_file_path, "rb") as f:
                encrypted_blob = f.read()
            return _win32_unprotect_data(encrypted_blob)
        else:
            raw_master = os.urandom(32)
            protected_blob = _win32_protect_data(raw_master)
            with open(key_file_path, "wb") as f:
                f.write(protected_blob)
            return raw_master

    @classmethod
    def encrypt_local_field(cls, master_key: bytes, value: str) -> str:
        """Cifra un campo del database locale con AES-256-GCM."""
        if not value:
            return ""
        c_b64, n_b64 = cls.encrypt_message(master_key, value)
        return f"{n_b64}:{c_b64}"

    @classmethod
    def decrypt_local_field(cls, master_key: bytes, encrypted_payload: str) -> str:
        """Decifra un campo dal database locale."""
        if not encrypted_payload or ":" not in encrypted_payload:
            return encrypted_payload
        n_b64, c_b64 = encrypted_payload.split(":", 1)
        try:
            return cls.decrypt_message(master_key, c_b64, n_b64)
        except Exception:
            return "[Errore Decifratura Locale]"
