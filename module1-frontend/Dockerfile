# syntax=docker/dockerfile:1
FROM node:22-alpine AS development

WORKDIR /app
COPY package*.json ./
# Optional trust bundle for environments with an HTTPS inspection proxy.
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --no-audit --no-fund

COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_APP_SURFACE=student
ENV NEXT_PUBLIC_APP_SURFACE=$NEXT_PUBLIC_APP_SURFACE
ARG PORT=3000
ENV PORT=$PORT
ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE ${PORT}
CMD ["sh", "-c", "npx next dev -p ${PORT}"]

FROM development AS build
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm run build

FROM node:22-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ARG PORT=3000
ENV PORT=$PORT
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE ${PORT}
CMD ["node", "server.js"]
