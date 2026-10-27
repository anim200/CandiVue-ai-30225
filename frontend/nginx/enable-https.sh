#!/bin/sh
# Runs when the container starts (nginx runs every script in
# /docker-entrypoint.d/). Turns HTTPS on only if a certificate was provided
# in the certs/ folder; otherwise the app stays HTTP on localhost only.

if [ -f /etc/nginx/certs/cert.pem ] && [ -f /etc/nginx/certs/key.pem ]; then
    cp /etc/nginx/optional/https.conf /etc/nginx/conf.d/https.conf
    echo "CandiVue: certificate found, HTTPS enabled"
else
    rm -f /etc/nginx/conf.d/https.conf
    echo "CandiVue: no certificate in certs/, HTTPS disabled (HTTP on localhost only)"
fi
