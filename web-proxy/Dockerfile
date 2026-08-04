FROM nginx:1.27-alpine

# Self-signed сертификат, чтобы прокси реально мог слушать 443 в учебном стенде
RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout /etc/nginx/certs/self.key \
        -out /etc/nginx/certs/self.crt \
        -days 365 -subj "/CN=localhost"

COPY nginx.conf /etc/nginx/nginx.conf