#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f "./install_nova_helper.sh" ]; then
  echo "install_nova_helper.sh was not found next to this file."
  echo "Download or clone the full car-sd-music-helper project first."
  echo
  read -r -n 1 -s -p "Press any key to close..."
  echo
  exit 1
fi

chmod +x ./install_nova_helper.sh
./install_nova_helper.sh

echo
echo "Done. Open:"
echo "https://d3xt3r2909.github.io/car-sd-music-helper/"
echo
read -r -n 1 -s -p "Press any key to close..."
echo
