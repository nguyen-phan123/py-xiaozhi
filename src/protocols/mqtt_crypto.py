"""Mã hóa/giải mã AES-CTR dùng cho kênh âm thanh MQTT/UDP."""

from __future__ import annotations

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def aes_ctr_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    """Mã hóa AES-CTR.

    Args:
        key: Khóa bí mật (secret key)
        nonce: Nonce khởi tạo (nhất quán khi giải mã)
        plaintext: Dữ liệu văn bản gốc (plaintext)
    """
    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def aes_ctr_decrypt(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """Giải mã AES-CTR.

    Args:
        key: Khóa bí mật (secret key)
        nonce: Nonce tương ứng khi mã hóa
        ciphertext: Dữ liệu đã mã hóa (ciphertext)
    """
    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def build_audio_nonce(aes_nonce_hex: str, audio_len: int, sequence: int) -> str:
    """Tạo nonce cho gói tin âm thanh UDP (chuỗi hex).

    Định dạng: Prefix cố định 4 hex + độ dài 4 hex + nonce gốc 16 hex + số thứ tự (sequence) 8 hex
    """
    return (
        aes_nonce_hex[:4]
        + format(audio_len, "04x")
        + aes_nonce_hex[8:24]
        + format(sequence, "08x")
    )
