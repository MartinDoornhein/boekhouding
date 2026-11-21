#!/usr/bin/env bash
# Jaararchief (bewaarplicht 7 jaar): maakt een zip met database + bonnen en zet die in
# s3://<bucket>/archief/. Die map valt buiten de Litestream-retentie en gaat na 30 dagen
# naar GLACIER (goedkope opslag). Draai bijvoorbeeld begin januari, na de laatste aangifte.
# Vereist de AWS CLI (brew install awscli); werkt met dezelfde sleutels als Litestream.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
: "${BOEKHOUDING_S3_BUCKET:?Zet BOEKHOUDING_S3_BUCKET in .env}"
: "${BOEKHOUDING_S3_REGION:?Zet BOEKHOUDING_S3_REGION in .env}"

FILE="$(mktemp -d)/boekhouding-archief-$(date +%Y-%m-%d).zip"
.venv/bin/flask --app boekhouding archive -o "$FILE"
AWS_ACCESS_KEY_ID="$LITESTREAM_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$LITESTREAM_SECRET_ACCESS_KEY" \
  aws s3 cp "$FILE" "s3://$BOEKHOUDING_S3_BUCKET/archief/$(basename "$FILE")" \
  --endpoint-url "https://s3.$BOEKHOUDING_S3_REGION.scw.cloud" --region "$BOEKHOUDING_S3_REGION"
echo "Archief geüpload: s3://$BOEKHOUDING_S3_BUCKET/archief/$(basename "$FILE")"
echo "Bewaar desgewenst ook een kopie op je NAS: $FILE"
