# certs/

Put the HTTPS certificate for the frontend here (optional):

- `cert.pem` – the certificate
- `key.pem` – its private key

The `.pem` files are git-ignored and must never be committed. Without them
the app runs on plain HTTP, bound to localhost only. See "Transport
security" in the main README for how to create them with mkcert.
