from email.header import decode_header


def decode_filename(filename):
    decoded = decode_header(filename)
    if decoded[0][1]:
        return decoded[0][0].decode(decoded[0][1])
    if isinstance(decoded[0][0], bytes):
        return decoded[0][0].decode()
    return decoded[0][0]