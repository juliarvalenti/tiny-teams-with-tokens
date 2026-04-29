FROM node:20-alpine

WORKDIR /app

# Install deps with the pinned lockfile (cached unless lockfile changes)
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci

# Then app code
COPY frontend ./

# Backend hostname inside the compose network
ENV TTT_API_URL=http://backend:8765

EXPOSE 3000

# Dev mode for the PoC: simpler, no build step, easy to iterate.
# Swap to `npm run build` + `npm start` if/when this graduates beyond a PoC.
CMD ["npx", "next", "dev", "-p", "3000", "-H", "0.0.0.0"]
