#!/bin/bash

SLM="slimcoind -testnet"
SLEEPTIME=30
RESTARTTIME=15

function bestpeerheight() {

  HEIGHTS=$("$SLM" getpeerinfo | grep "height" | grep -Eo "[0-9]*" | paste -sd " ")
  HMAX=0

  for HEIGHT in $HEIGHTS
  do
    if [ "$HEIGHT" -gt "$HMAX" ]; then
      HMAX="$HEIGHT"
    fi
  done

  echo "$HMAX"
}

function currentheight() {

  "$SLM" getblockcount

}

BEST=$(bestpeerheight)
CURRENT=$(currentheight)

if [ "$1" == "verbose" ]; then
  echo "Best height: $BEST"
  echo "Current height: $CURRENT"
fi

if [ "$BEST" -gt "$CURRENT" ]; then

  sleep "$SLEEPTIME"
  BEST=$(bestpeerheight)
  CURRENT=$(currentheight)

  if [ "$BEST" -gt "$CURRENT" ]; then
    if [ "$1" == "verbose" ]; then
      echo "Restarting ..."
    fi

    "$SLM" stop
    sleep "$RESTARTTIME"
    "$SLM"
  fi
fi
