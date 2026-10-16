FROM node:22-alpine AS build

WORKDIR /srv/frontend

COPY package.json package-lock.json* ./
RUN npm install

COPY tsconfig.json tsconfig.node.json vite.config.ts index.html ./
COPY src ./src
COPY tests ./tests

# 类型检查 + 单测 + 产物构建；任何一步失败都让镜像构建失败
RUN npx vitest run && npm run build

FROM nginx:1.27-alpine

COPY --from=build /srv/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
