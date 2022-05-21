#!/usr/bin/env python3
from __future__ import annotations

from typing import Tuple, BinaryIO, Type

import base64
import hashlib
import io
import shutil

import obsolete_cryptography as ocrypt

from . import constants

BytesLike = bytes | bytearray | memoryview

safersk128 = ocrypt.CipherModule('safer-sk128')
ripemd256 = ocrypt.HashModule('ripemd256')


class SaferSK128FVCBC:
    '''
    Homebrew Propagating-CBC-based (?) mode.
    '''

    _key: bytes
    _iv: bytes
    _ctx: ocrypt.mcrypt.MCrypt
    _feedback: int
    _state: str

    def __init__(self, key: bytes, iv: bytes):
        self._key = key
        self._iv = iv
        self._ctx = safersk128.new(key, 'ecb')
        self._feedback = int.from_bytes(iv, 'big')
        self._state = 'initialized'

    def _update_feedback(self, block: bytes):
        block_int = int.from_bytes(block, 'big')
        self._feedback ^= block_int

    def _toggle_cbc(self, data):
        return (int.from_bytes(data, 'big') ^ self._feedback).to_bytes(8, 'big')

    def _split_data(self, data: BytesLike) -> Tuple[bytes, bytes]:
        # TODO figure out how to pass memoryviews to cython
        aligned_size = (len(data) // 8) * 8
        unaligned_size = len(data) - aligned_size
        aligned_data = memoryview(data)[:aligned_size]
        unaligned_data = memoryview(data)[aligned_size:]
        return aligned_data.tobytes(), unaligned_data.tobytes()

    @classmethod
    def from_passphrase(cls: Type[SaferSK128FVCBC], passphrase: str) -> SaferSK128FVCBC:
        key = derive_key(passphrase)
        iv = derive_iv(key)

        return cls(key, iv)

    def create_cfb_finisher(self):
        return safersk128.new(self._key, 'ncfb', IV=self._feedback.to_bytes(8, 'big'))

    def encrypt(self, data: BytesLike) -> bytes:
        if len(data) % 8 != 0:
            raise ValueError('Block length is not a multiple of 8. Hint: use '
                             'create_cfb_finisher for last block of length < 8.')

        if self._state == 'decrypting':
            raise RuntimeError('Cannot encrypt using an decryption context.')
        self._state = 'encrypting'

        data_io = io.BytesIO(data)
        ct_io = io.BytesIO()

        while True:
            pt = data_io.read(8)
            if len(pt) < 8:
                break

            # Do the normal CBC op
            pt_cbc = self._toggle_cbc(pt)
            ct = self._ctx.encrypt(pt_cbc)
            ct_io.write(ct)

            # Propagation with feedback = feedback ^ ciphertext (instead of
            # feedback = plaintext ^ ciphertext in regular PCBC mode)
            self._update_feedback(ct)

        return ct_io.getvalue()

    def decrypt(self, data: BytesLike) -> bytes:
        if len(data) % 8 != 0:
            raise ValueError('Block length is not a multiple of 8. Hint: use '
                             'create_cfb_finisher for last block of length < 8.')

        if self._state == 'encrypting':
            raise RuntimeError('Cannot decrypt using an encryption context.')
        self._state = 'decrypting'

        data_io = io.BytesIO(data)
        pt_io = io.BytesIO()

        while True:
            ct = data_io.read(8)
            if len(ct) < 8:
                break

            # Do the normal CBC op
            pt_cbc = self._ctx.decrypt(ct)
            pt = self._toggle_cbc(pt_cbc)
            pt_io.write(pt)

            # Propagation with feedback = feedback ^ ciphertext (instead of
            # feedback = plaintext ^ ciphertext in regular PCBC mode)
            self._update_feedback(ct)

        return pt_io.getvalue()

    def encrypt_autofinish(self, data: BytesLike) -> bytes:
        if len(data) % 8 == 0:
            return self.encrypt(data)

        result = io.BytesIO()

        aligned_data, unaligned_data = self._split_data(data)

        result.write(self.encrypt(aligned_data))
        result.write(self.create_cfb_finisher().encrypt(unaligned_data))
        return result.getvalue()

    def decrypt_autofinish(self, data: BytesLike) -> bytes:
        if len(data) % 8 == 0:
            return self.decrypt(data)

        result = io.BytesIO()

        aligned_data, unaligned_data = self._split_data(data)

        result.write(self.decrypt(aligned_data))
        result.write(self.create_cfb_finisher().decrypt(unaligned_data))
        return result.getvalue()


def derive_key(passphrase: str):
    return ripemd256.new(passphrase.encode('utf-8')).digest()[:16]

def derive_iv(key: bytes):
    return safersk128.new(key, 'ecb').encrypt(b'\xff' * 8)

def ddmd5(data: BytesLike | str) -> str:
    '''
    Double data MD5 (md5(data+data)) used to derive the passphrase for book
    password encryption.
    Corresponding method: FVUtil.getMD5Value()
    '''
    data_bytes = data.encode('utf-8') if isinstance(data, str) else data
    md5 = hashlib.md5(data_bytes)
    md5.update(data_bytes)
    return md5.hexdigest()

def derive_passphrase_access_code(passphrase: str) -> str:
    '''
    Derive passphrase used to encrypt book password from license master
    passphrase.
    '''
    return ddmd5((passphrase + constants.PASSWORD_PASSPHRASE_SUFFIX).encode('utf-8'))

def decrypt_hex_b64_str(passphrase: str, string: str) -> str:
    '''
    Unwrap the ciphertext and decrpyt it as a UTF-8 string.
    '''
    key = derive_key(passphrase)
    iv = derive_iv(key)

    cipher = SaferSK128FVCBC(key, iv)
    ct = base64.b64decode(bytes.fromhex(string))
    pt_bytes = cipher.decrypt_autofinish(ct)

    try:
        pt = pt_bytes.decode('utf-8')
    except UnicodeDecodeError as e:
        raise ValueError('Decryption failed. Wrong key?') from e

    return pt

def encrypt_hex_b64_str(passphrase: str, string: str) -> str:
    '''
    Encrypt a string and wrap it in base64 then hex.
    '''
    key = derive_key(passphrase)
    iv = derive_iv(key)

    cipher = SaferSK128FVCBC(key, iv)
    pt_bytes = string.encode('utf-8')
    ct = cipher.encrypt_autofinish(pt_bytes)

    return base64.b64encode(ct).hex().upper()

def decrypt_offline_license_passphrase(epassphrase: str) -> str:
    return decrypt_hex_b64_str(constants.OFFLINE_LICENSE_PASSPHRASE, epassphrase)

def encrypt_offline_license_passphrase(passphrase: str) -> str:
    return encrypt_hex_b64_str(constants.OFFLINE_LICENSE_PASSPHRASE, passphrase)

def decrypt_access_code_passphrase(passphrase: str, epassword: str) -> str:
    password_passphrase = derive_passphrase_access_code(passphrase)
    return decrypt_hex_b64_str(password_passphrase, epassword)

def encrypt_access_code_passphrase(passphrase: str, password: str) -> str:
    password_passphrase = derive_passphrase_access_code(passphrase)
    return encrypt_hex_b64_str(password_passphrase, password)

def decrypt_swf_obj_file(passphrase: str, in_file: BinaryIO, out_file: BinaryIO) -> None:
    cipher = SaferSK128FVCBC.from_passphrase(passphrase)

    block = in_file.read(8192)
    out_file.write(cipher.decrypt_autofinish(block))

    # Only the first 8KiB is encrypted. Copy any leftover data to the output if they exist.
    if len(block) == 8192:
        shutil.copyfileobj(in_file, out_file)

def encrypt_swf_obj_file(passphrase: str, in_file: BinaryIO, out_file: BinaryIO) -> None:
    cipher = SaferSK128FVCBC.from_passphrase(passphrase)

    block = in_file.read(8192)
    out_file.write(cipher.encrypt_autofinish(block))

    # Only the first 8KiB is encrypted. Copy any leftover data to the output if they exist.
    if len(block) == 8192:
        shutil.copyfileobj(in_file, out_file)
