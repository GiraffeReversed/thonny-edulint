#!/bin/bash

BASEDIR_RELATIVE=$(dirname "$0")
BASEDIR=$(realpath $BASEDIR_RELATIVE)

THONNY_PATH=$BASEDIR/thonny
echo $THONNY_PATH

PLUGIN_PATH=$(realpath $BASEDIR/..)
echo $PLUGIN_PATH

export PYTHONPATH=$PLUGIN_PATH

cd $THONNY_PATH
python3 -m thonny
