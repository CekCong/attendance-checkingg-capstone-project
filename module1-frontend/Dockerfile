FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ARG NEXT_PUBLIC_APP_SURFACE=student
ENV NEXT_PUBLIC_APP_SURFACE=$NEXT_PUBLIC_APP_SURFACE

ARG PORT=3000
ENV PORT=$PORT

RUN npm run build

EXPOSE ${PORT}

CMD ["sh", "-c", "npx next start -p ${PORT}"]
