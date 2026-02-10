FROM node:18-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy source
COPY server.js ./

EXPOSE 8001

CMD ["node", "server.js"]
