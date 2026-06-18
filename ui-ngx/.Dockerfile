FROM node:22-slim

RUN apt update

RUN apt install git curl -y

RUN npm i -g @angular/cli

WORKDIR /app/ui-ngx

CMD ["sh", "-c", "yarn start"]
