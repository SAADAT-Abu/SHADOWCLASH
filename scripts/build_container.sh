#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "Building SHADOWCLASH Singularity image..."
sudo singularity build shadowclash.sif Singularity.def
echo "Build complete: shadowclash.sif"
echo "Share this single file — recipients only need Singularity/Apptainer installed."
