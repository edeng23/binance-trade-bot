#!/bin/bash
set -e

# Create the config file if it doesn't exist
CONFIG=/app/user.cfg
if [ ! -f "${CONFIG}" ]; then
    cp /app/.user.cfg.example /app/user.cfg
fi

# Substitute config with environment variables (keep in sync with .user.cfg.example)
sed -i "s|api_key=.*|api_key=${API_KEY}|g" $CONFIG
sed -i "s|api_secret_key=.*|api_secret_key=${API_SECRET_KEY}|g" $CONFIG
sed -i "s|current_coin=.*|current_coin=${CURRENT_COIN}|g" $CONFIG
sed -i "s|bridge=.*|bridge=${BRIDGE_CURRENCY}|g" $CONFIG
sed -i "s|tld=.*|tld=${TLD:-com}|g" $CONFIG
sed -i "s|hourToKeepScoutHistory=.*|hourToKeepScoutHistory=${HOURS_TO_KEEP_SCOUTING_HISTORY:-1}|g" $CONFIG
sed -i "s|scout_transaction_fee=.*|scout_transaction_fee=${SCOUT_TRANSACTION_FEE:-0.001}|g" $CONFIG
sed -i "s|scout_multiplier=.*|scout_multiplier=${SCOUT_MULTIPLIER:-5}|g" $CONFIG
sed -i "s|scout_sleep_time=.*|scout_sleep_time=${SCOUT_SLEEP_TIME:-5}|g" $CONFIG

exec "$@"