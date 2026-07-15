#!/bin/sh
set -e

if [ ! -d node_modules ]; then
    echo 'Installing node_modules...' && yarn install --non-interactive --check-files --network-concurrency 4 --network-timeout 100000 --mutex network --ignore-engines
fi

echo 'Bundling split OpenAPI spec...'
mkdir -p /tmp/openapi-split
cp -r ../api-specs/openapi/* /tmp/openapi-split/
npx --yes @redocly/cli bundle /tmp/openapi-split/openapi.yaml --output /tmp/openapi.yaml --ext yaml 2>/dev/null || true
echo 'Generating API client from OpenAPI spec...'
openapi-generator-cli generate -i /tmp/openapi.yaml -g typescript-angular -o src/app/core/api-client --additional-properties=providedInRoot=true,ngVersion=20,supportsES6=true
asyncapi generate models typescript ../api-specs/asyncapi.yaml -o src/app/core/event-models --tsModelType interface --tsExportType named --tsEnumType union --tsIncludeComments --no-interactive --tsRawPropertyNames

node --max_old_space_size=8048 ./node_modules/@angular/cli/bin/ng serve \
    --configuration development \
    --host 0.0.0.0 \
    --port 4200 \
    --proxy-config proxy.conf.docker-dev.js \
    --live-reload true \
    --poll 1000
