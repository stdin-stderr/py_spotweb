import hashlib
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend


def spot_unprepare_base64(data: str) -> bytes:
    """Decode Spotnet's custom base64 escaping.

    Spotnet uses: / → _, + → -
    Standard base64 uses: / → /, + → +
    """
    standard = data.replace('_', '/').replace('-', '+')
    missing_padding = len(standard) % 4
    if missing_padding:
        standard += '=' * (4 - missing_padding)
    return base64.b64decode(standard)


def verify_hashcash(message_id: str) -> bool:
    """Verify Spotnet hashcash proof-of-work.

    Hashcash is: sha1(<messageid>) starting with "0000"
    """
    if not message_id.startswith('<'):
        message_id = f'<{message_id}>'

    hash_hex = hashlib.sha1(message_id.encode()).hexdigest()
    return hash_hex.startswith('0000')


def verify_rsa_signature(message: bytes, signature: bytes, modulo: str, exponent: str = 'AQAB') -> bool:
    """Verify an RSA signature using public key components.

    Args:
        message: The message that was signed (bytes)
        signature: The RSA signature to verify (bytes)
        modulo: Base64-encoded RSA modulus (N)
        exponent: Base64-encoded RSA public exponent (e), default 'AQAB' = 65537

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        n = int.from_bytes(spot_unprepare_base64(modulo), byteorder='big')

        if exponent == 'AQAB':
            e = 65537
        else:
            e = int.from_bytes(spot_unprepare_base64(exponent), byteorder='big')

        public_key = rsa.RSAPublicNumbers(e, n).public_key(default_backend())

        public_key.verify(
            signature,
            message,
            padding.PKCS1v15(),
            hashes.SHA1()
        )
        return True
    except Exception:
        return False


def calculate_spotter_id(public_key_modulo: str) -> str:
    """Calculate a unique spotter ID from the user's public key.

    This creates a unique identifier for the poster based on their public key.
    """
    try:
        key_bytes = spot_unprepare_base64(public_key_modulo)
        sha1_hash = hashlib.sha1(key_bytes).hexdigest()
        return sha1_hash[:16]
    except Exception:
        return None


def verify_spot_signature(spot: dict, message_id_from_nntp: str) -> tuple[bool, str | None]:
    """Verify a Spotnet post signature.

    Args:
        spot: Dictionary with keys: keyid, headersign, selfsignedpubkey (optional)
        message_id_from_nntp: Message ID from NNTP headers

    Returns:
        Tuple of (verified: bool, spotter_id: str|None)
    """
    msg_id = message_id_from_nntp
    if not msg_id.startswith('<'):
        msg_id = f'<{msg_id}>'

    key_id = spot.get('keyid')
    signature_b64 = spot.get('headersign')

    if not signature_b64 or key_id is None:
        return False, None

    try:
        signature = spot_unprepare_base64(signature_b64)
    except Exception:
        return False, None

    # SPOTSIGN_V2: Self-signed with hashcash
    if key_id == 7:
        if not verify_hashcash(msg_id):
            return False, None

        selfsigned_pubkey = spot.get('selfsignedpubkey')
        if not selfsigned_pubkey:
            return False, None

        verified = verify_rsa_signature(
            msg_id.encode(),
            signature,
            selfsigned_pubkey,
            'AQAB'
        )

        if verified:
            spotter_id = calculate_spotter_id(selfsigned_pubkey)
            return True, spotter_id
        return False, None

    # SPOTSIGN_V1: Pre-established key verification
    else:
        known_keys = {
            2: {
                'modulo': 'ys8WSlqonQMWT8ubG0tAA2Q07P36E+CJmb875wSR1XH7IFhEi0CCwlUzNqBFhC+P',
                'exponent': 'AQAB'
            },
            3: {
                'modulo': 'uiyChPV23eguLAJNttC/o0nAsxXgdjtvUvidV2JL+hjNzc4Tc/PPo2JdYvsqUsat',
                'exponent': 'AQAB'
            },
            4: {
                'modulo': '1k6RNDVD6yBYWR6kHmwzmSud7JkNV4SMigBrs+jFgOK5Ldzwl17mKXJhl+su/GR9',
                'exponent': 'AQAB'
            }
        }

        if key_id not in known_keys:
            return False, None

        key = known_keys[key_id]

        verified = verify_rsa_signature(
            str(key_id).encode(),
            signature,
            key['modulo'],
            key['exponent']
        )

        return verified, None
