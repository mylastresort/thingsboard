FROM node:22-slim

RUN apt update

RUN apt install -y git curl default-jre-headless

RUN npm i -g @angular/cli

WORKDIR /app/ui-ngx

CMD ["sh", "-c", "yarn start"]
