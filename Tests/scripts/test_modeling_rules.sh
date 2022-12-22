#!/bin/bash

XSIAM_SERVERS_PATH=${XSIAM_SERVERS_PATH:-"xsiam_servers.json"}

# Get XSIAM Tenant Config Details
XSIAM_SERVER_CONFIG=$(jq -r ".[\"$XSIAM_CHOSEN_MACHINE_ID\"]" < "$XSIAM_SERVERS_PATH")
XSIAM_URL=$(echo "$XSIAM_SERVER_CONFIG" | jq -r ".[\"base_url\"]")
AUTH_ID=$(echo "$XSIAM_SERVER_CONFIG" | jq -r ".[\"x-xdr-auth-id\"]")
API_KEY=$(jq -r ".[\"$XSIAM_CHOSEN_MACHINE_ID\"]" < "$XSIAM_API_KEYS")
XSIAM_TOKEN=$(jq -r ".[\"$XSIAM_CHOSEN_MACHINE_ID\"]" < "$XSIAM_TOKENS")

MODELING_RULES_ARRAY=($(cat "$ARTIFACTS_FOLDER"/modeling_rules_to_test.txt))
for modeling_rule in "${MODELING_RULES_ARRAY[@]}"; do
    if [[ -n "$MODELING_RULES_TO_TEST" ]]; then
        MODELING_RULES_TO_TEST="$MODELING_RULES_TO_TEST Packs/$modeling_rule"
    else
        MODELING_RULES_TO_TEST="Packs/$modeling_rule"
    fi
done

if [[ -z "$MODELING_RULES_TO_TEST" ]]; then
    echo "There was a problem reading the list of modeling rules that require testing from '$ARTIFACTS_FOLDER/modeling_rules_to_test.txt'"
    exit 1
fi

echo "XSIAM_URL=$XSIAM_URL"
echo "AUTH_ID=$AUTH_ID"
echo "DEMISTO_BASE_URL=$DEMISTO_BASE_URL"
echo "XSIAM_AUTH_ID=$XSIAM_AUTH_ID"
echo "XSIAM_TOKEN=${XSIAM_TOKEN:(-8)}"

echo "Testing Modeling Rules"
demisto-sdk modeling-rules test -vvv --xsiam-url="$XSIAM_URL" --auth-id="$AUTH_ID" --api-key="$API_KEY" --xsiam-token="$XSIAM_TOKEN" --non-interactive $(echo "$MODELING_RULES_TO_TEST")
