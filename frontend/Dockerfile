FROM node:22-alpine

WORKDIR /app
COPY package.json ./
RUN npm install

COPY . .

# NEXT_PUBLIC_* はビルド時にクライアントバンドルへ埋め込まれるため、ここで明示する。
# 本番は nginx が /api をルーティングするので同一オリジンの /api を既定とする。
ARG NEXT_PUBLIC_API_BASE=/api
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
