#!/bin/bash

cd $(dirname "$0")

## Oficial edulint setup
# https://github.com/thonny/thonny/wiki/Plugins#an-example-setup-with-linux-commands

git clone https://github.com/thonny/thonny

## Futher setup
# https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps
# test WSL GUI
sudo apt update && sudo apt install gnome-text-editor -y && gnome-text-editor
sudo apt install python3-tk

python3 -m pip install edulint

