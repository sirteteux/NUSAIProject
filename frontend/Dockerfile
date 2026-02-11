FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build-time argument for API Gateway URL
ARG VITE_API_GATEWAY_URL=http://localhost:8000
ENV VITE_API_GATEWAY_URL=$VITE_API_GATEWAY_URL

# Build the application
RUN npm run build

# Install serve to run the built app
RUN npm install -g serve

# Expose port
EXPOSE 3000

# Start the application
CMD ["serve", "-s", "dist", "-l", "3000"]
