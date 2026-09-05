# node 24 y no 20: el lockfile lo escribe npm 11 y la imagen de node 20 trae
# npm 10, que lo rechaza con "lock file ... does not satisfy". El error salta
# en `npm ci`, asi que el contenedor no se podia construir.
FROM node:24-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
# Nunca root. La imagen de node ya trae el usuario `node`; hace falta cederle
# el arbol porque la compilacion corrio como root y Next escribe su cache en
# `.next` durante la ejecucion.
RUN chown -R node:node /app
USER node
EXPOSE 3000
CMD ["npm", "start"]
