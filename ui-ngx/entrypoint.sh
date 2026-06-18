if [ ! -d node_modules ]; then
    echo 'Installing node_modules...' && yarn install --non-interactive --check-files --network-concurrency 4 --network-timeout 100000 --mutex network
fi &&
node --max_old_space_size=8048 ./node_modules/@angular/cli/bin/ng serve \
    --configuration development \
    --host 0.0.0.0 \
    --port 4200 \
    --proxy-config proxy.conf.docker-dev.js \
    --live-reload true \
    --poll 1000