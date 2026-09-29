"""Hand-labelled questions over the RFC corpus (data/real_corpus). Every quote is a verbatim sentence taken from the
cleaned RFC text (eval.real_corpus.clean). Run `python -m eval.build_real_golden` to (re)write and verify the file."""
import json

from core import config
from eval import real_corpus, scorer

Q = {  # key -> (doc, verbatim quote)
    "iss": ("RFC 7519", 'The "iss" (issuer) claim identifies the principal that issued the JWT.'),
    "exp": ("RFC 7519", 'The "exp" (expiration time) claim identifies the expiration time on or after which the JWT MUST NOT be accepted for processing.'),
    "code": ("RFC 6749", "A maximum authorization code lifetime of 10 minutes is RECOMMENDED."),
    "state": ("RFC 6749", "An opaque value used by the client to maintain state between the request and callback."),
    "rec": ("RFC 8446", "length MUST NOT exceed 2^14 bytes."),
    "replay": ("RFC 8446", "The server MUST ensure that any instance of it (be it a machine, a thread, or any other entity within the relevant serving infrastructure) would accept 0-RTT for the same 0-RTT handshake at most once; this limits the number of replays to the number of server instances in the deployment."),
    "init": ("RFC 9000", "A client MUST expand the payload of all UDP datagrams carrying Initial packets to at least the smallest allowed maximum datagram size of 1200 bytes"),
    "cid": ("RFC 9000", "In QUIC version 1, this value MUST NOT exceed 20 bytes."),
    "guid": ("RFC 6455", "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"),
    "close": ("RFC 6455", "1000 indicates a normal closure, meaning that the purpose for which the connection was established has been fulfilled."),
    "udp": ("RFC 1035", "Messages carried by UDP are restricted to 512 bytes (not counting the IP or UDP headers)."),
    "label": ("RFC 1035", "Labels must be 63 characters or less."),
    "msl": ("RFC 793", "Maximum Segment Lifetime, the time a TCP segment can exist in the internetwork system. Arbitrarily defined to be 2 minutes."),
    "local": ("RFC 5321", "The maximum total length of a user name or other local-part is 64 octets."),
    "reply": ("RFC 5321", "The maximum total length of a reply line including the reply code and the <CRLF> is 512 octets."),
    "416": ("RFC 7233", "The 416 (Range Not Satisfiable) status code indicates that none of the ranges in the request's Range header field"),
    "delims": ("RFC 3986", 'gen-delims = ":" / "/" / "?" / "#" / "[" / "]" / "@"'),
    "cookie": ("RFC 6265", "At least 4096 bytes per cookie (as measured by the sum of the length of the cookie's name, value, and attributes)."),
    "secure": ("RFC 6265", 'The Secure attribute limits the scope of the cookie to "secure" channels'),
}
ITEMS = [  # (question, gold answer, evidence keys)
    ("Which registered JWT claim says who created and signed the token?", "The \"iss\" (issuer) claim", ["iss"]),
    ("After what point must a JWT no longer be accepted?", "On or after the time in the \"exp\" (expiration time) claim", ["exp"]),
    ("For how long, at most, should an OAuth 2.0 authorization code remain valid?", "10 minutes", ["code"]),
    ("What is the purpose of the state parameter in an OAuth authorization request?", "An opaque value the client uses to maintain state between the request and the callback", ["state"]),
    ("What is the largest fragment a TLS 1.3 plaintext record may carry?", "2^14 bytes", ["rec"]),
    ("How does TLS 1.3 limit replay of 0-RTT early data across a fleet of servers?", "Each server instance must accept the same 0-RTT handshake at most once, limiting replays to the number of instances", ["replay"]),
    ("What is the minimum size a QUIC client must pad its Initial datagrams to?", "1200 bytes", ["init"]),
    ("How long can a connection ID be in QUIC version 1?", "At most 20 bytes", ["cid"]),
    ("What fixed string is appended to the Sec-WebSocket-Key when computing the server handshake response?", "The GUID 258EAFA5-E914-47DA-95CA-C5AB0DC85B11", ["guid"]),
    ("What does WebSocket close status code 1000 mean?", "Normal closure: the purpose of the connection has been fulfilled", ["close"]),
    ("What is the size limit for a DNS message sent over UDP?", "512 bytes (excluding IP and UDP headers)", ["udp"]),
    ("How long is a TCP segment assumed to be able to survive in the network?", "The Maximum Segment Lifetime, defined as 2 minutes", ["msl"]),
    ("How many octets may the local part of an email address have in SMTP?", "64 octets", ["local"]),
    ("Which HTTP status code is returned when none of the requested byte ranges can be served?", "416 (Range Not Satisfiable)", ["416"]),
    ("Which characters does the URI syntax treat as general delimiters?", ": / ? # [ ] @", ["delims"]),
    ("What are the maximum lengths of a DNS label and an SMTP local-part?", "63 characters for a DNS label; 64 octets for an SMTP local-part", ["label", "local"]),
    ("What size limit applies to classic DNS-over-UDP messages, and what size must QUIC Initial datagrams reach?", "512 bytes for DNS over UDP; at least 1200 bytes for QUIC Initial datagrams", ["udp", "init"]),
    ("For HTTP cookies, what minimum per-cookie size must a client support, and what does the Secure attribute restrict a cookie to?", "At least 4096 bytes per cookie; the Secure attribute limits it to secure channels", ["cookie", "secure"]),
    ("When must a JWT stop being accepted, and how long can an OAuth authorization code live?", "A JWT is rejected on or after its exp time; an authorization code lives at most 10 minutes (recommended)", ["exp", "code"]),
    ("How long does TCP assume a segment lives in the network, and how long can an SMTP reply line be?", "2 minutes (MSL); 512 octets", ["msl", "reply"]),
]


def build():
    return [{"id": i, "question": q, "answer": a, "type": "multi" if len(ks) > 1 else "single",
             "evidence": [{"doc": Q[k][0], "quote": Q[k][1]} for k in ks]} for i, (q, a, ks) in enumerate(ITEMS, 1)]


if __name__ == "__main__":
    text = {p.stem.replace("_", " "): scorer.norm(real_corpus.clean(p.read_text(encoding="utf-8", errors="ignore")))
            for p in real_corpus.files()}
    items = build()
    bad = [(it["id"], e["quote"][:50]) for it in items for e in it["evidence"] if scorer.norm(e["quote"]) not in text[e["doc"]]]
    assert not bad, f"quotes not found verbatim: {bad}"
    (config.ROOT / "eval" / "real_golden_set.json").write_text(json.dumps(items, indent=2), encoding="utf-8")
    print(len(items), "questions;", sum(i["type"] == "multi" for i in items), "multi; all quotes verified")
