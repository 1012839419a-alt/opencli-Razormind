FROM node:26-alpine AS dependencies

WORKDIR /app
RUN npm install --global pnpm@11.18.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM dependencies AS builder

ARG BACKEND_URL=http://api:8000
ARG NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS
ARG NEXT_PUBLIC_API_AUTH_TOKEN
ARG NEXT_PUBLIC_YJS_URL
ENV BACKEND_URL=${BACKEND_URL} \
    NEXT_PUBLIC_API_AUTH_TOKEN=${NEXT_PUBLIC_API_AUTH_TOKEN} \
    NEXT_PUBLIC_YJS_URL=${NEXT_PUBLIC_YJS_URL} \
    NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS=${NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS} \
    NEXT_TELEMETRY_DISABLED=1
COPY . .
RUN pnpm build

FROM node:26-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3010
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3010
CMD ["node", "server.js"]
